import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from app import create_app, initialize

PASSWORD = 'test-password-for-tests-only'

class SalesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credentials = {'username':'owner','password_hash':generate_password_hash(PASSWORD),'secret_key':'test-secret-not-for-production-' * 2}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'sales.sqlite3'
        self.app = create_app(self.db, self.credentials, production=False)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/session').json['csrf']

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, password=PASSWORD):
        response = self.client.post('/api/login', json={'username':'owner','password':password}, headers={'X-CSRF-Token':self.csrf})
        if response.status_code == 200:
            self.csrf = response.json['csrf']
        return response

    def send(self, method, path='/api/sales', data=None, **kwargs):
        return self.client.open(path, method=method, json=data, headers={'X-CSRF-Token':self.csrf, **kwargs})

    def test_anonymous_cannot_read_or_change_sales(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get('/api/sales').status_code, 401)
        for method, path in [('POST','/api/sales'),('PUT','/api/sales/1'),('DELETE','/api/sales/1')]:
            self.assertEqual(self.send(method,path,{}).status_code,401)
        self.assertFalse(self.client.get('/api/session').json['authenticated'])
        self.assertEqual(self.client.get('/healthz').status_code,200)
        with self.client.get('/login') as response:
            self.assertEqual(response.status_code,200)

    def test_crud_and_persistence(self):
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.client.get('/api/sales').json,[])
        response = self.send('POST',data={'date':'2026-11-02','product':' カフェラテ ','amount':'550'})
        self.assertEqual(response.status_code,201)
        sale_id=response.json['id']
        self.send('POST',data={'date':'2026-11-01','product':'ケーキ','amount':650})
        rows=self.client.get('/api/sales').json
        self.assertEqual(rows[0],{'id':sale_id,'date':'2026-11-02','product':'カフェラテ','amount':550})
        self.assertEqual(sum(row['amount'] for row in rows),1200)
        initialize(self.db)
        # A newly created app uses the same database and can read existing records.
        restored=create_app(self.db,self.credentials,production=False).test_client()
        token=restored.get('/api/session').json['csrf']
        self.assertEqual(restored.post('/api/login',json={'username':'owner','password':PASSWORD},headers={'X-CSRF-Token':token}).status_code,200)
        self.assertEqual(len(restored.get('/api/sales').json),2)
        self.assertEqual(self.send('PUT',f'/api/sales/{sale_id}',{'date':'2026-10-31','product':'コーヒー','amount':400}).status_code,200)
        self.assertEqual(self.client.get('/api/sales').json[-1]['amount'],400)
        self.assertEqual(self.send('DELETE',f'/api/sales/{sale_id}').status_code,200)
        self.assertEqual(len(self.client.get('/api/sales').json),1)
        self.assertEqual(self.send('DELETE',f'/api/sales/{sale_id}').status_code,404)
        self.assertEqual(self.send('DELETE','/api/sales/9999999999999999999999999').status_code,404)

    def test_invalid_input_does_not_write(self):
        self.login()
        base={'date':'2026-11-02','product':'コーヒー','amount':400}
        for field,value in [('date','2026-02-30'),('date','20261102'),('date',None),('product','  '),('product','a'*101),('amount',0),('amount',-1),('amount','1.5'),('amount',True),('amount','NaN'),('amount','Infinity'),('amount',1000000000)]:
            with self.subTest(field=field,value=value):
                self.assertEqual(self.send('POST',data={**base,field:value}).status_code,400)
        self.assertEqual(self.send('POST',data=[]).status_code,400)
        self.assertEqual(self.client.get('/api/sales').json,[])

    def test_csrf_and_origin(self):
        self.login()
        data={'date':'2026-11-02','product':'コーヒー','amount':400}
        self.assertEqual(self.client.post('/api/sales',json=data).status_code,403)
        self.assertEqual(self.send('POST',data=data,Origin='https://other.example').status_code,403)
        self.assertEqual(self.send('POST',data=data,**{'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.post('/api/sales',data='{}',content_type='text/plain',headers={'X-CSRF-Token':self.csrf}).status_code,415)
        self.assertEqual(self.client.post('/api/logout').status_code,403)
        self.assertEqual(self.client.post('/api/login',json={'username':'owner','password':PASSWORD}).status_code,403)

    def test_bad_password_and_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.login('wrong-password').status_code,401)
        self.assertEqual(self.login().status_code,429)
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE login_attempts SET started=?',(int(time.time())-901,))
        self.assertEqual(self.login().status_code,200)

    def test_logout_revokes_copied_cookie(self):
        self.login()
        stolen=self.client.get_cookie('mcafe').value
        self.assertEqual(self.client.get('/api/sales').status_code,200)
        self.assertEqual(self.send('POST','/api/logout',{}).status_code,200)
        self.client.set_cookie('mcafe',stolen)
        self.assertEqual(self.client.get('/api/sales').status_code,401)

    def test_expired_and_forged_sessions(self):
        self.login()
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.client.get('/api/sales').status_code,401)
        self.client.set_cookie('mcafe','forged-cookie')
        self.assertEqual(self.client.get('/api/sales').status_code,401)

    def test_static_assets_and_headers(self):
        self.login()
        for path,expected in [('/',b'lang="ja"'),('/app.js',b'renderList'),('/sales.mjs',b'aggregate'),('/style.css',b'@media')]:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn(expected,response.data)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            response.close()
        self.assertEqual(self.client.get('/../app.py').status_code,404)
        self.assertEqual(self.client.get('/data/sales.sqlite3').status_code,404)

    def test_production_cookie_and_https(self):
        client=create_app(self.db,self.credentials,production=True).test_client()
        self.assertEqual(client.get('/api/session').status_code,400)
        response=client.get('/api/session',base_url='https://example.test')
        self.assertEqual(response.status_code,200)
        cookie=response.headers['Set-Cookie']
        for flag in ['__Host-mcafe','Secure','HttpOnly','SameSite=Lax','Path=/']:
            self.assertIn(flag,cookie)
        self.assertIn('Strict-Transport-Security',response.headers)
        self.assertEqual(client.get('/healthz').status_code,200)

    def test_production_requires_real_configuration(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(RuntimeError):
                create_app(self.db,production=True)

if __name__=='__main__':
    unittest.main()
