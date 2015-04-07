# Copyright (C) 2015  Custodia Project Contributors - see LICENSE file

from custodia.httpd.consumer import HTTPConsumer
from custodia.httpd.server import HTTPError
from custodia.store.interface import CSStoreError
import json
import os


class Secrets(HTTPConsumer):

    def _get_key(self, namespaces, trail):
        # Check tht the keys is in one of the authorized namespaces
        if len(trail) < 1 or trail[0] not in namespaces:
            raise HTTPError(403)
        # pylint: disable=star-args
        return os.path.join('keys', *trail)

    def _get_filter(self, namespaces, trail, userfilter):
        f = None
        if len(trail) > 0:
            for ns in namespaces:
                if ns == trail[0]:
                    f = self._get_key(namespaces, trail)
                break
            if f is None:
                raise HTTPError(403)
        else:
            # Consider the first namespace as the default one
            t = [namespaces[0]] + trail
            f = self._get_key(namespaces, t)
        return '%s/%s' % (f, userfilter)

    def _validate(self, value):
        try:
            msg = json.loads(value)
        except Exception:
            raise ValueError('Invalid JSON in payload')
        if 'type' not in msg:
            raise ValueError('Message type missing')
        if msg['type'] != 'simple':
            raise ValueError('Message type unknown')
        if 'value' not in msg:
            raise ValueError('Message value missing')
        if len(msg.keys()) != 2:
            raise ValueError('Unknown attributes in Message')

    def _namespaces(self, request):
        if 'remote_user' not in request:
            raise HTTPError(403)
        # At the moment we just have one namespace, the user's name
        return [request['remote_user']]

    def GET(self, request, response):
        trail = request.get('trail', [])
        ns = self._namespaces(request)
        if len(trail) == 0 or trail[-1] == '':
            try:
                userfilter = request.get('query', dict()).get('filter', '')
                keyfilter = self._get_filter(ns, trail[:-1], userfilter)
                keydict = self.root.store.list(keyfilter)
                if keydict is None:
                    raise HTTPError(404)
                output = dict()
                for k in keydict:
                    # strip away the internal prefix for storing keys
                    name = k[len('keys/'):]
                    value = keydict[k]
                    # remove the containers themselves, we list only keys
                    if name.endswith('/'):
                        continue
                    if value == '':
                        output[name] = ''
                    else:
                        output[name] = json.loads(value)
                response['output'] = json.dumps(output)
            except CSStoreError:
                raise HTTPError(404)
        else:
            key = self._get_key(ns, trail)
            try:
                output = self.root.store.get(key)
                if output is None:
                    raise HTTPError(404)
                response['output'] = output
            except CSStoreError:
                raise HTTPError(500)

    def PUT(self, request, response):
        trail = request.get('trail', [])
        ns = self._namespaces(request)
        if len(trail) == 0 or trail[-1] == '':
            raise HTTPError(405)

        content_type = request.get('headers',
                                   dict()).get('Content-Type', '')
        if content_type.split(';')[0].strip() != 'application/json':
            raise HTTPError(400, 'Invalid Content-Type')
        body = request.get('body')
        if body is None:
            raise HTTPError(400)
        value = bytes(body).decode('utf-8')
        try:
            self._validate(value)
        except ValueError as e:
            raise HTTPError(400, str(e))

        # must _get_key first as access control is done here for now
        # otherwise users would e able to probe containers in namespaces
        # they do not have access to.
        key = self._get_key(ns, trail)

        try:
            # check that the containers exist
            n = 0
            for n in range(1, len(trail)):
                probe = self._get_key(ns, trail[:n] + [''])
                try:
                    check = self.root.store.get(probe)
                    if check is None:
                        break
                except CSStoreError:
                    break
            # create if default namespace
            if n == 1 and ns[0] == trail[0]:
                self.root.store.set(probe, '')
            else:
                raise HTTPError(404)

            self.root.store.set(key, value)
        except CSStoreError:
            raise HTTPError(500)

        response['code'] = 201


# unit tests
import unittest
from custodia.store.sqlite import SqliteStore


class SecretsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.secrets = Secrets()
        cls.secrets.root.store = SqliteStore({'dburi': 'testdb.sqlite'})

    @classmethod
    def tearDownClass(self):
        try:
            os.unlink('testdb.sqlite')
        except OSError:
            pass

    def test_0_LISTkey_404(self):
        req = {'remote_user': 'test',
               'trail': ['test', '']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.GET(req, rep)

        self.assertEqual(err.exception.code, 404)

    def test_1_PUTKey(self):
        req = {'headers': {'Content-Type': 'application/json'},
               'remote_user': 'test',
               'trail': ['test', 'key1'],
               'body': '{"type":"simple","value":"1234"}'}
        rep = {}
        self.secrets.PUT(req, rep)

    def test_2_GETKey(self):
        req = {'remote_user': 'test',
               'trail': ['test', 'key1']}
        rep = {}
        self.secrets.GET(req, rep)
        self.assertEqual(rep['output'],
                         '{"type":"simple","value":"1234"}')

    def test_3_LISTKeys(self):
        req = {'remote_user': 'test',
               'trail': ['test', '']}
        rep = {}
        self.secrets.GET(req, rep)
        self.assertEqual(json.loads(rep['output']),
                         json.loads('{"test/key1":'\
                                    '{"type":"simple","value":"1234"}}'))

    def test_3_LISTKeys_2(self):
        req = {'remote_user': 'test',
               'query': {'filter': 'key'},
               'trail': ['test', '']}
        rep = {}
        self.secrets.GET(req, rep)
        self.assertEqual(json.loads(rep['output']),
                         json.loads('{"test/key1":'\
                                    '{"type":"simple","value":"1234"}}'))

    def test_4_PUTKey_errors_400_1(self):
        req = {'headers': {'Content-Type': 'text/plain'},
               'remote_user': 'test',
               'trail': ['test', 'key2'],
               'body': '{"type":"simple","value":"2345"}'}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 400)

    def test_4_PUTKey_errors_400_2(self):
        req = {'headers': {'Content-Type': 'text/plain'},
               'remote_user': 'test',
               'trail': ['test', 'key2']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 400)

    def test_4_PUTKey_errors_400_3(self):
        req = {'headers': {'Content-Type': 'text/plain'},
               'remote_user': 'test',
               'trail': ['test', 'key2'],
               'body': '{"type":}"simple","value":"2345"}'}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 400)

    def test_4_PUTKey_errors_403(self):
        req = {'headers': {'Content-Type': 'application/json; charset=utf-8'},
               'remote_user': 'test',
               'trail': ['case', 'key2'],
               'body': '{"type":"simple","value":"2345"}'}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 403)

    def test_4_PUTKey_errors_404(self):
        req = {'headers': {'Content-Type': 'application/json; charset=utf-8'},
               'remote_user': 'test',
               'trail': ['test', 'more', 'key1'],
               'body': '{"type":"simple","value":"1234"}'}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 404)

    def test_4_PUTKey_errors_405(self):
        req = {'headers': {'Content-Type': 'application/json; charset=utf-8'},
               'remote_user': 'test',
               'trail': ['test', 'key2', ''],
               'body': '{"type":"simple","value":"2345"}'}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.PUT(req, rep)
        self.assertEqual(err.exception.code, 405)

    def test_5_GETKey_errors_403(self):
        req = {'remote_user': 'case',
               'trail': ['test', 'key1']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.GET(req, rep)
        self.assertEqual(err.exception.code, 403)

    def test_5_GETkey_errors_404(self):
        req = {'remote_user': 'test',
               'trail': ['test', 'key0']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.GET(req, rep)

        self.assertEqual(err.exception.code, 404)

    def test_6_LISTkeys_errors_404_1(self):
        req = {'remote_user': 'test',
               'trail': ['test', 'case', '']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.GET(req, rep)
        self.assertEqual(err.exception.code, 404)

    def test_6_LISTkeys_errors_404_2(self):
        req = {'remote_user': 'test',
               'query': {'filter': 'foo'},
               'trail': ['test', '']}
        rep = {}
        with self.assertRaises(HTTPError) as err:
            self.secrets.GET(req, rep)
        self.assertEqual(err.exception.code, 404)

