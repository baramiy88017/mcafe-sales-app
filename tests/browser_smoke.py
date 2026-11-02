"""Optional browser smoke check. Requires Playwright and a Chromium install."""
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as temp:
        password = secrets.token_urlsafe(24)
        credentials = {'username':'test-owner','password_hash':generate_password_hash(password),'secret_key':secrets.token_urlsafe(48)}
        app = create_app(Path(temp) / 'sales.sqlite3', credentials, production=False)
        server = make_server('127.0.0.1', 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width':1440,'height':1100},locale='ja-JP')
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = f'http://127.0.0.1:{server.server_port}'
                page.goto(url)
                expect(page.locator('#login-form')).to_be_visible()
                expect(page.locator('#login-button')).to_be_enabled()
                page.locator('#username').fill('test-owner')
                page.locator('#password').fill('wrong-password')
                page.locator('#login-button').click()
                expect(page.locator('#login-error')).to_be_visible()
                page.locator('#password').fill(password)
                page.locator('#login-button').click()
                expect(page.locator('#all-total')).to_have_text('￥0')
                page.locator('#add-sale').click()
                page.locator('#sale-date').fill('2026-11-02')
                page.locator('#sale-product').fill('カフェラテ')
                page.locator('#sale-amount').fill('550')
                page.locator('#save-sale').click()
                expect(page.locator('#sales-body tr')).to_have_count(1)
                expect(page.locator('#all-total')).to_have_text('￥550')
                page.reload()
                expect(page.locator('#sales-body tr')).to_have_count(1)
                page.locator('.edit-button').click()
                page.locator('#sale-amount').fill('650')
                page.locator('#save-sale').click()
                expect(page.locator('#all-total')).to_have_text('￥650')
                page.locator('#monthly').click()
                expect(page.locator('#chart')).to_contain_text('2026/11')
                page.locator('#search').fill('該当なし')
                expect(page.locator('#sales-body tr')).to_have_count(0)
                expect(page.locator('#filtered-total')).to_have_text('￥0')
                page.locator('#reset-filters').click()
                expect(page.locator('#sales-body tr')).to_have_count(1)
                page.screenshot(path='/tmp/mcafe-auth-desktop.png',full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('.delete-button').click()
                page.locator('#cancel-delete').click()
                expect(page.locator('#sales-body tr')).to_have_count(1)
                page.locator('.delete-button').click()
                page.locator('#confirm-delete').click()
                expect(page.locator('#sales-body tr')).to_have_count(0)
                expect(page.locator('#all-total')).to_have_text('￥0')
                page.locator('#logout').click()
                expect(page.locator('#login-form')).to_be_visible()
                page.goto(url + '/api/sales')
                assert page.locator('body').inner_text().find('ログインしてください') >= 0
                page.goto(url)
                expect(page.locator('#login-form')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path='/tmp/mcafe-login-mobile.png',full_page=True)
                assert not errors, errors
                browser.close()
                print('PASS: login failure/success, create/edit/delete, persistence, totals, search, mobile, logout and anonymous access denial; no JavaScript errors.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
