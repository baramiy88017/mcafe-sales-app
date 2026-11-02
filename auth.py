"""Single-shop authentication, CSRF protection and server-side sessions."""
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time

from flask import jsonify, redirect, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

SESSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW = 15 * 60
LOGIN_LIMIT = 10


def load_credentials(data_dir, production):
    username = os.environ.get('ADMIN_USERNAME', '')
    password = os.environ.get('ADMIN_PASSWORD', '')
    secret = os.environ.get('SECRET_KEY', '')
    if production or any((username, password, secret)):
        if not username.strip() or len(username) > 100 or len(password) < 12 or len(password) > 256 or len(secret) < 32:
            raise RuntimeError('ADMIN_USERNAME、12〜256文字のADMIN_PASSWORD、32文字以上のSECRET_KEYを設定してください。')
        return {'username': username, 'password_hash': generate_password_hash(password), 'secret_key': secret}
    path = Path(data_dir) / 'auth.json'
    if not path.exists():
        raise RuntimeError('先に python manage.py create-user を実行してログイン情報を設定してください。')
    return json.loads(path.read_text())


def configure_auth(app, get_db, credentials, production):
    app.config.update(
        SECRET_KEY=credentials['secret_key'],
        SESSION_COOKIE_NAME='__Host-mcafe' if production else 'mcafe',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=SESSION_SECONDS),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=8192,
    )
    if production and os.environ.get('TRUST_PROXY') == '1':
        # Only enable behind the hosting provider's trusted, single reverse proxy.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    # A credential change or process restart invalidates existing sessions.
    auth_version = hashlib.sha256(credentials['password_hash'].encode()).hexdigest()

    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def authenticated():
        token = session.get('token')
        if not isinstance(token, str):
            return False
        row = get_db().execute('SELECT expires, version FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return row is not None and row['expires'] > time.time() and hmac.compare_digest(row['version'], auth_version)

    @app.before_request
    def protect():
        if production and not request.is_secure and request.path != '/healthz':
            return jsonify(error='HTTPSでアクセスしてください。'), 400
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin != request.host_url.rstrip('/')):
                return jsonify(error='この操作は許可されていません。'), 403
            expected_csrf = session.get('csrf')
            if not expected_csrf or not hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode(), expected_csrf.encode()):
                return jsonify(error='画面を再読み込みして、もう一度操作してください。'), 403
        public = {'/healthz', '/login', '/login.js', '/style.css', '/api/session', '/api/login'}
        if request.path not in public and not authenticated():
            if request.path.startswith('/api/'):
                return jsonify(error='ログインしてください。'), 401
            return redirect('/login')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.get('/api/session')
    def current_session():
        logged_in = authenticated()
        return jsonify(authenticated=logged_in, username=credentials['username'] if logged_in else None, csrf=csrf_token())

    @app.post('/api/login')
    def login():
        if not request.is_json:
            return jsonify(error='JSON形式で送信してください。'), 415
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify(error='入力内容を確認してください。'), 400
        username, password = data.get('username'), data.get('password')
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 256:
            return jsonify(error='ユーザー名またはパスワードが違います。'), 401
        now = int(time.time())
        key = request.remote_addr or 'unknown'
        db = get_db()
        db.execute('DELETE FROM login_attempts WHERE started < ?', (now - LOGIN_WINDOW,))
        db.execute('DELETE FROM sessions WHERE expires < ?', (now,))
        db.commit()
        attempt = db.execute('SELECT failures FROM login_attempts WHERE address=?', (key,)).fetchone()
        if attempt and attempt['failures'] >= LOGIN_LIMIT:
            response = jsonify(error='ログインの失敗が続いたため、15分ほど待ってからお試しください。')
            response.headers['Retry-After'] = str(LOGIN_WINDOW)
            return response, 429
        password_ok = check_password_hash(credentials['password_hash'], password)
        if not (hmac.compare_digest(username.encode(), credentials['username'].encode()) and password_ok):
            db.execute('INSERT INTO login_attempts(address, failures, started) VALUES (?, 1, ?) ON CONFLICT(address) DO UPDATE SET failures=failures+1', (key, now))
            db.commit()
            return jsonify(error='ユーザー名またはパスワードが違います。'), 401
        old_token = session.get('token')
        if old_token:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(old_token.encode()).hexdigest(),))
        session.clear()
        session.permanent = True
        token = secrets.token_urlsafe(32)
        session['token'] = token
        db.execute('INSERT INTO sessions(token_hash, expires, version) VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), now + SESSION_SECONDS, auth_version))
        db.execute('DELETE FROM login_attempts WHERE address=?', (key,))
        db.commit()
        return jsonify(authenticated=True, csrf=csrf_token())

    @app.post('/api/logout')
    def logout():
        token = session.get('token', '')
        db = get_db()
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        db.commit()
        session.clear()
        return jsonify(ok=True)
