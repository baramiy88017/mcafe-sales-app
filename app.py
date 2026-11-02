"""M Cafe sales manager: authenticated Flask application."""
import argparse
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from auth import configure_auth, load_credentials

ROOT = Path(__file__).resolve().parent


def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, product TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, version TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
            address TEXT PRIMARY KEY, failures INTEGER NOT NULL, started INTEGER NOT NULL
        )""")


def validate_sale(body):
    if not isinstance(body, dict):
        raise ValueError("入力内容を確認してください。")
    day, product, amount = body.get("date"), body.get("product"), body.get("amount")
    try:
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("正しい日付を入力してください。") from None
    if not isinstance(product, str) or not product.strip() or len(product.strip()) > 100:
        raise ValueError("商品名は1〜100文字で入力してください。")
    try:
        if isinstance(amount, bool) or not isinstance(amount, (str, int)):
            raise InvalidOperation()
        number = Decimal(str(amount))
        if not number.is_finite() or number != number.to_integral_value() or not 1 <= number <= 999999999:
            raise InvalidOperation()
    except (InvalidOperation, ValueError):
        raise ValueError("金額は1〜999,999,999円の整数で入力してください。") from None
    return day, product.strip(), int(number)



def create_app(db_path=None, credentials=None, production=None):
    production = os.environ.get('APP_ENV') == 'production' if production is None else production
    db_path = Path(db_path or os.environ.get('DATABASE_PATH', ROOT / 'data' / 'sales.sqlite3'))
    initialize(db_path)
    credentials = credentials or load_credentials(db_path.parent, production)
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    def get_db():
        if 'db' not in g:
            g.db = connect(db_path)
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    configure_auth(app, get_db, credentials, production)

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400: '入力データを読み取れません。', 404: 'ページが見つかりません。', 405: 'この操作には対応していません。', 413: '送信データが大きすぎます。'}
        return jsonify(error=messages.get(error.code, '操作に失敗しました。')), error.code

    @app.get('/healthz')
    def health():
        get_db().execute('SELECT 1 FROM sales LIMIT 1').fetchone()
        return jsonify(status='ok')

    @app.get('/login')
    def login_page():
        return send_from_directory(ROOT / 'static', 'login.html')

    @app.get('/')
    def index():
        return send_from_directory(ROOT / 'static', 'index.html')

    @app.get('/<filename>')
    def asset(filename):
        if filename not in {'app.js', 'sales.mjs', 'style.css', 'login.js'}:
            return jsonify(error='ページが見つかりません。'), 404
        return send_from_directory(ROOT / 'static', filename)

    @app.route('/api/sales', methods=['GET', 'POST'])
    @app.route('/api/sales/<int:sale_id>', methods=['PUT', 'DELETE'])
    def sales(sale_id=None):
        db = get_db()
        if request.method == 'GET':
            rows = db.execute('SELECT id, date, product, amount FROM sales ORDER BY date DESC, id DESC').fetchall()
            return jsonify([dict(row) for row in rows])
        if sale_id is not None and sale_id > 9223372036854775807:
            return jsonify(error='売上が見つかりません。'), 404
        values = None
        if request.method != 'DELETE':
            if not request.is_json:
                return jsonify(error='JSON形式で送信してください。'), 415
            try:
                values = validate_sale(request.get_json())
            except ValueError as error:
                return jsonify(error=str(error)), 400
        if request.method == 'POST':
            cursor = db.execute('INSERT INTO sales(date, product, amount) VALUES (?, ?, ?)', values)
            sale_id = cursor.lastrowid
        elif request.method == 'PUT':
            cursor = db.execute('UPDATE sales SET date=?, product=?, amount=? WHERE id=?', (*values, sale_id))
        else:
            cursor = db.execute('DELETE FROM sales WHERE id=?', (sale_id,))
        if cursor.rowcount == 0:
            return jsonify(error='売上が見つかりません。画面を再読み込みしてください。'), 404
        db.commit()
        return jsonify(id=sale_id), 201 if request.method == 'POST' else 200

    return app


def main():
    parser = argparse.ArgumentParser(description='M Cafe 売上管理')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', type=Path)
    args = parser.parse_args()
    create_app(args.db).run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
