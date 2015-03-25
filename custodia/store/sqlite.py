# Copyright (C) 2015  Custodia Project Contributors - see LICENSE file

from custodia.store.interface import CSStore, CSStoreError
import os
import sqlite3
import sys


def log_error(error):
    print >> sys.stderr, error


class SqliteStore(CSStore):

    def __init__(self, config):
        if 'dburi' not in config:
            raise ValueError('Missing "dburi" for Sqlite Store')
        self.dburi = config['dburi']
        if 'table' in config:
            self.table = config['table']
        else:
            self.table = "CustodiaSecrets"

    def get(self, key):
        query = "SELECT value from %s WHERE key=?" % self.table
        try:
            conn = sqlite3.connect(self.dburi)
            c = conn.cursor()
            r = c.execute(query, (key))
            value = r.fetchall()
        except sqlite3.Error as err:
            log_error("Error fetching key %s: [%r]" % (key, repr(err)))
            raise CSStoreError('Error occurred while trying to get key')
        return value

    def _create(self, cur):
        create = "CREATE TABLE IF NOT EXISTS %s (key, value)" % self.table
        cur.execute(create)

    def set(self, key, value):
        setdata = "INSERT OR REPLACE into %s VALUES (?, ?)" % self.table
        try:
            conn = sqlite3.connect(self.dburi)
            with conn:
                c = conn.cursor()
                self._create(c)
                c.execute(setdata, (key, value))
        except sqlite3.Error as err:
            log_error("Error storing key %s: [%r]" % (key, repr(err)))
            raise CSStoreError('Error occurred while trying to store key')

    def list(self, keyfilter='/'):
        search = "SELECT * FROM %s WHERE key LIKE ?" % self.table
        key = os.path.join(keyfilter, '%')
        try:
            conn = sqlite3.connect(self.dburi)
            r = conn.execute(search, (key,))
            value = r.fetchall()
        except sqlite3.Error as err:
            log_error("Error listing (filter: %s): [%r]" % (key, repr(err)))
            raise CSStoreError('Error occurred while trying to list keys')
        return value