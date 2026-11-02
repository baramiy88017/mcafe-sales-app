"""Create or reset local login credentials without displaying passwords."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import sqlite3
from contextlib import closing
from werkzeug.security import generate_password_hash
from app import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['create-user', 'backup'])
    parser.add_argument('destination', nargs='?', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    if args.command == 'backup':
        if args.destination is None:
            parser.error('バックアップ先のファイル名を指定してください。')
        source = Path(os.environ.get('DATABASE_PATH', args.data_dir / 'sales.sqlite3')).resolve()
        destination = args.destination
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
                with closing(sqlite3.connect(destination)) as backup:
                    original.backup(backup)
        except Exception:
            destination.unlink()
            raise
        print('バックアップを保存しました。')
        return
    if args.destination is not None:
        parser.error('create-userには保存先ファイルを指定しません。')
    username = input('ユーザー名: ').strip()
    if not username or len(username) > 100:
        parser.error('ユーザー名は1〜100文字で入力してください。')
    password = getpass.getpass('パスワード（12文字以上）: ')
    if not 12 <= len(password) <= 256:
        parser.error('パスワードは12〜256文字で入力してください。')
    if password != getpass.getpass('パスワード（確認）: '):
        parser.error('パスワードが一致しません。')
    args.data_dir.mkdir(parents=True, exist_ok=True)
    path = args.data_dir / 'auth.json'
    if path.exists() and input('既存のログイン情報を変更しますか？ [yes/N]: ') != 'yes':
        return
    # A private temporary file and atomic replacement protect interrupted updates.
    temp = args.data_dir / f'.auth-{secrets.token_hex(8)}.tmp'
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
        json.dump({'username': username, 'password_hash': generate_password_hash(password), 'secret_key': secrets.token_urlsafe(48)}, file)
    os.replace(temp, path)
    print('ログイン情報を保存しました。アプリを起動（または再起動）してください。')


if __name__ == '__main__':
    main()
