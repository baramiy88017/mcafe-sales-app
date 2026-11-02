import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from werkzeug.security import check_password_hash
from app import initialize
import manage

class ManageTests(unittest.TestCase):
    def test_create_user_stores_hash_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            with patch('sys.argv',['manage.py','create-user','--data-dir',temp]), patch('builtins.input',return_value='owner'), patch('getpass.getpass',return_value='test-password-12345'), contextlib.redirect_stdout(io.StringIO()):
                manage.main()
            path = data / 'auth.json'
            credentials = json.loads(path.read_text())
            self.assertTrue(check_password_hash(credentials['password_hash'],'test-password-12345'))
            self.assertNotIn('test-password-12345',path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_backup_preserves_sales_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'sales.sqlite3'
            destination = Path(temp) / 'backup.sqlite3'
            initialize(source)
            with sqlite3.connect(source) as db:
                db.execute('INSERT INTO sales(date, product, amount) VALUES (?, ?, ?)',('2026-11-02','カフェラテ',550))
            arguments = ['manage.py','backup',str(destination),'--data-dir',temp]
            with patch('sys.argv',arguments), patch.dict(os.environ,{'DATABASE_PATH':str(source)}), contextlib.redirect_stdout(io.StringIO()):
                manage.main()
                with self.assertRaises(FileExistsError):
                    manage.main()
            with sqlite3.connect(destination) as backup:
                self.assertEqual(backup.execute('SELECT product,amount FROM sales').fetchone(),('カフェラテ',550))
            self.assertEqual(destination.stat().st_mode & 0o777,0o600)

    def test_missing_backup_source_does_not_create_empty_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'backup.sqlite3'
            with patch('sys.argv',['manage.py','backup',str(destination),'--data-dir',temp]), patch.dict(os.environ,{'DATABASE_PATH':str(Path(temp)/'missing.sqlite3')}):
                with self.assertRaises(sqlite3.OperationalError):
                    manage.main()
            self.assertFalse(destination.exists())

if __name__=='__main__':
    unittest.main()
