# -*- coding: utf-8 -*-

"""PyDbWrapper

TODO: 
    
"""

import os
import re
import sys
import pdb
import time
import MySQLdb
import ConfigParser

sys.exit('asdasd')

class PyDbWrapper:

    def __init__(self, connInfo, **opts):
        """
            :params dict connInfo: database credentials and user info.
                Required keys are user, password, dbname, host; optional is 
                port that is set to default value of 3306
            :params dict opts: optional parameters.
        """

        # additional options
        opts = dict({}, **opts) 

        self._connInfo = dict({
            'host'      : None,
            'dbname'    : None,
            'port'      : 3306,
            'user'      : None,
            'password'  : None,
            }, 
            **connInfo)
        self._conn          = None
        self._opts          = opts
        self.query          = None
        self.sql_no_cache   = False
        self.autocommit     = True
        self.sqlCacheOn     = True
        self.lastInsertId   = None
        self.charset        = 'utf8'
        self.info           = {
            'executed': [],
            'connStats': None,
            'lastInsertId': None,
            'totalExecutionTime': None
        }

        # check if neccesary connection data is set
        if all(self._connInfo.get(k, False) for k in ('host','user','password','dbname')):
            pass
        else:
            raise ValueError('One or more connection parameters missing, required are: ' + ', '.join(connInfoRequired))

    def _connection(self):
        """Will create new database connection if not already established
        """
        if self._conn and self._conn.open:
            return

        try:
            self._conn = MySQLdb.connect(
                host    = self._connInfo.get('host'),
                port    = self._connInfo.get('port'),
                user    = self._connInfo.get('user'),
                passwd  = self._connInfo.get('password'),
                db      = self._connInfo.get('dbname'),
                charset = self.charset
            )

        except MySQLdb.Error, e:
            raise PyDbWrapperException('There was a problem with connection to the database: ' + str(e))

    def _fetch(self, query, **opts):
        """Fetches first or all records returned from cursor object
            :params string query: sql query
            :params dict opts: optional parameters
                - returnDict: return data as dictionary
                - fetchType: "first" or "all"
        """

        opts = dict({'returnDict': True}, **opts)

        # If sql_no_cache is set to true
        # alter the query to include SQL_NO_CACHE directive
        if self.sql_no_cache == True:
            query = re.sub(r'SELECT\s', 'SELECT SQL_NO_CACHE ', query, 1, flags=re.IGNORECASE)

        # Check/reestablish connection
        self._connection()
        # Return data in a form of dictionary
        if opts['returnDict'] == True:
            cur = self._conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        else:
            cur = self._conn.cursor()

        t0 = time.time() # start time
        cur.execute(query)
        if opts.get('fetchType') == 'first':
            rows = cur.fetchone()
        elif opts.get('fetchType') == 'all':
            rows = cur.fetchall()
        else:
            raise PyDbWrapperException('Unknown fetchType')
        t1 = time.time() - t0 # end time

        self._setInfo(cur, time=t1) # store time

        cur.close()
        return rows

    def fetchFirst(self, query, **opts):
        return self._fetch(query, fetchType='first', **opts)

    def fetchAll(self, query, **opts):
        return self._fetch(query, fetchType='all', **opts)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def execute(self, query, data=None, **opts):
        """Executes passed SQL query

            :param string query: MySQL string to be executed
            :param dict data: if passed sql query is in tokenized form data has to be passed
                as well; data parameter has to be of dict type and contains all the keys
                that will replace tokens in the passed string  
            :param dict opts: optional parameters
        """

        opts = dict({'returnSQL': False}, **opts)

        # create the connection
        self._connection()
        cur = self._conn.cursor()

        if data and query:
            replaceData = []

            # Find columns to fillout in SQL statement
            p = re.compile('\[(.+?)\]')
            cols = p.findall(query)

            for col in cols:

                try:
                    val = data[col]
                except KeyError, e:
                    raise PyDbWrapperError('Missing value for referenced column "' + col + '"')

                query = query.replace('[' + col + ']', '`' + col + '` = %s')

                replaceData.append(val)

            # Execute SQL with tokens
            if opts['returnSQL'] == True:
                return query % tuple(replaceData)

            t0 = time.time()
            cur.execute(query, tuple(replaceData))
            t1 = time.time() - t0

            self._setInfo(cur, time=t1)
            cur.close()

        elif query:
            # Execute passed raw SQL query
            if opts['returnSQL'] == True:
                return query
            # Exectue SQL query
            t0 = time.time()
            cur.execute(query)
            t1 = time.time() - t0

            self._setInfo(cur, time=t1)
            cur.close()

        else:
            raise PyDbWrapperError('Expecting 1st parameter to be SQL query.')

        # If autocommit it True
        # otherwise commit() method has to be run explicitly
        if self.autocommit:
            self.commit()

    def _setInfo(self, cur, **opts):
        """This internal method is run each time query is executed.
        Is stores some info about query execution.

            :param object cur: curson object
            :param dict opts: optional parameters
        """

        opts = dict({}, **opts)

        self.lastInsertId = cur.lastrowid
        self.info['executed'].append(
            {
                'query': cur._last_executed,
                'lastInsertId': cur.lastrowid,
                'warnings': cur._warnings,
                'executionTime': opts['time']
            }
        )
        self.info['connStats'] = self._conn.stat()
        self.info['lastInsertId'] = cur.lastrowid

        totalTime = 0
        for executed in self.info['executed']:
            totalTime += executed['executionTime']

        self.info['totalExecutionTime'] = totalTime

    def __del__(self):
        pass

class PyDbWrapperError(Exception): pass