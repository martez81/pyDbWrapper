# -*- coding: utf-8 -*-

"""PyDbWrapper
		 
"""

import os
import re
import sys
import pdb
import time
import MySQLdb

class PyDbWrapper(object):
    _instance = None

    def __new__(cls, connInfo, **opts):
        if cls._instance != None:
            cls._instance.debug('Reusing singleton object')
            return cls._instance
        else:
            return super(PyDbWrapper, cls).__new__(cls)

    def __init__(self, connInfo, **opts):
        """:params dict connInfo: database credentials and user info.
                Required keys are user, password, dbname, host; optional is 
                port that is set to default value of 3306
            :params dict opts: optional parameters.
        """

        # additional options
        opts = dict({}, **opts) 

        self._connInfo  = dict({
            'host'      : None,
            'dbname'    : None,
            'port'      : 3306,
            'user'      : None,
            'password'  : None,
            }, 
            **connInfo)
        self.debugMode          = True
        self._conn              = None
        self._opts              = opts
        self.query              = None
        self.sql_no_cache       = False
        self.autocommit         = True
        self.lastInsertId       = None
        self.charset            = 'utf8'
        self.reuseConnection    = True
        self.infoSizeLimit      = 200
        self.info               = {
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

    @classmethod
    def singleton(cls, connInfo, **opts):
        cls._instance = cls(connInfo, **opts)
        return cls._instance 

    def connect(self):
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
            raise PyDbWrapperError('There was a problem with connecting to the database: %s' % e)

    def _fetch(self, query, **opts):
        """Fetches first or all records returned from cursor object
            :params string query: sql query
            :params dict opts: optional parameters
                - returnDict: return data as dictionary
                - fetchType: "first" or "all"
        """

        opts = dict({'returnDict': True}, **opts)

        # Clean query from formatting (lines, spaces etc.)
        query = self.cleanString(query)

        # If sql_no_cache is set to true
        # alter the query to include SQL_NO_CACHE directive
        if self.sql_no_cache == True:
            query = re.sub(r'SELECT\s', 'SELECT SQL_NO_CACHE ', query, 1, flags=re.IGNORECASE)

        # Check/reestablish connection if needed
        self.connect()

        # Return data in a form of dictionary
        if opts['returnDict'] == True:
            cur = self._conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        else:
            cur = self._conn.cursor()

        try:
            cur.execute(query)
        except MySQLdb.OperationalError, e:
            raise PyDbWrapperError('Problem executing this query: %s' % e)      
        
        t0 = time.time() # start time

        if opts.get('fetchType') == 'first':
            rows = cur.fetchone()
        elif opts.get('fetchType') == 'all':
            rows = cur.fetchall()
        else:
            raise PyDbWrapperError('Unknown fetchType')

        t1 = time.time() - t0 # end time

        self._setInfo(cur, time=t1) # store time

        cur.close()

        if self.reuseConnection == False:
            self.close()

        return rows

    def fetchFirst(self, query, **opts):
        data = self._fetch(query, fetchType='first', **opts)

        return data

    def fetchAll(self, query, **opts):
        data = self._fetch(query, fetchType='all', **opts)

        return data

    def commit(self):
        self._conn.commit()

        if self.reuseConnection == False:
            self.close()

    def rollback(self):
        self._conn.rollback()

        if self.reuseConnection == False:
            self.close()

    def close(self):
        if self._conn:
            self._conn.close()   
            self._conn = None
            self.debug('...connection closed')

    def cleanString(self, sqlString):
        return ' '.join([x.strip() for x in sqlString.splitlines() if x.strip() != ''])

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
        self.connect()
        cur = self._conn.cursor()

        # Clean query from formatting (lines, spaces etc.)
        query = self.cleanString(query)

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
        elif query:
            if opts['returnSQL'] == True:
                return query
        else:
            raise PyDbWrapperError('Expecting 1st parameter to be SQL query.')

        t0 = time.time()
        try:
            # Execute query
            if data:
                cur.execute(query, tuple(replaceData))
            else:
                cur.execute(query)
        except MySQLdb.OperationalError, e:
            self.close()
            raise PyDbWrapperError('Problem executing this query: %s, query %s' % (e, cur._last_executed))

        t1 = time.time() - t0

        self._setInfo(cur, time=t1)
        cur.close()

        # If autocommit it True
        # otherwise commit() method has to be run explicitly
        if self.autocommit:
            self.commit()

    def debug(self, message):
        if self.debugMode:
            print message

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

        # Check the size of the list.
        # If it's to big truncate it from the bottom.
        if len(self.info) > self.infoSizeLimit:
            self.info = self.info[1:]


        self.info['connStats'] = self._conn.stat()
        self.info['lastInsertId'] = cur.lastrowid

        totalTime = 0
        for executed in self.info['executed']:
            totalTime += executed['executionTime']

        self.info['totalExecutionTime'] = totalTime

    def __del__(self):
        self.close()
            
class PyDbWrapperError(Exception): 
    pass
