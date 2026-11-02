# M Cafe 売上管理アプリ

ログインして日付・商品名・金額を登録し、売上一覧の編集・削除と日別／月別集計ができる、日本語のWebアプリです。お店で使う1つのログインアカウントを想定しています。

## URLから使う（Renderに公開）

公開にはRenderのアカウントが必要です。`render.yaml` に、ログイン付きアプリと売上データを残すための保存領域を設定しています。**Webサービスと保存領域は有料です。作成画面に出る料金を確認してから進めてください。**

1. このリポジトリのアプリと `render.yaml` をGitHubに保存します。ローカルの変更だけではRenderから読み込めません。
2. [Render](https://dashboard.render.com/) に登録・ログインし、GitHubを接続します。
3. 「New」→「Blueprint」で `baramiy88017/mcafe-sales-app` を選び、アプリを保存したブランチを指定します。
4. `ADMIN_PASSWORD` に **12〜256文字のパスワード**を設定します。チャットやGitHubには書かず、Renderの設定画面で入力してください。ユーザー名は `owner` です。
5. 表示される料金を確認し、作成します。初回のビルドが終わり「Live」になったら、サービス画面の `https://…onrender.com` を開き、`owner` と設定したパスワードでログインします。

URLはRenderが作成します。作成前には確定しません。GitHubのアプリ変更は勝手に公開せず、Renderの「Manual Deploy」で反映する設定です。環境設定の公開は、Renderへのアプリ公開とは別です。

ログインできない場合はRenderの Environment で `ADMIN_USERNAME` / `ADMIN_PASSWORD` を確認・変更し、保存して再デプロイしてください。パスワード変更後やアプリの再起動後は再ログインが必要です。

### 公開時の設定

- `APP_ENV=production`：HTTPSのみ。必要なログイン情報が未設定なら起動しません。
- `SECRET_KEY`：Renderが自動生成。ログイン用Cookieの改ざん防止に使用。
- `ADMIN_USERNAME=owner` / `ADMIN_PASSWORD`：管理者のログイン情報。
- `DATABASE_PATH=/var/data/sales.sqlite3`：Renderの永続ディスク内に売上を保存。
- `TRUST_PROXY=1`：RenderのHTTPS中継を利用。信頼できる中継サーバーがない場所では指定しないでください。
- Gunicornは1ワーカー・4スレッド。単一インスタンス用です。

HTTPS、HttpOnly/Secure/SameSite Cookie、8時間のログイン期限、ログアウト時のセッション失効、CSRF対策、IPごとのログイン失敗回数制限（15分間に10回）を備えています。登録画面で誰でもアカウントを作れる機能はありません。複数店舗・権限分け・パスワード再設定メールは未対応です。

## 手元・開発環境で起動

Python 3.12以上を使用します。

```sh
cd /workspace/mcafe-sales-app
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py create-user
.venv/bin/python app.py --port 8000
```

`create-user` でユーザー名と12文字以上のパスワードを入力します。パスワードは画面に表示されず、ハッシュ化して `data/auth.json` に保存します。このファイルはGit管理対象外です。変更する場合は同じコマンドを実行してアプリを再起動してください。

公開用サーバーと同じ起動方法：

```sh
.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 30
```

開発環境で外部のポート接続が必要な場合は bind を `0.0.0.0:8000` に変更してください。ローカル用HTTP設定をインターネットへ直接公開しないでください。

## 機能

- ログイン・ログアウト、ログインしていないアクセスからの売上保護
- 売上の登録・修正・削除（削除前に確認）
- 今日・今月・累計の売上金額と件数
- 日別（売上がある直近7日）／月別（売上がある直近6か月）の集計
- 商品名検索・日付範囲の絞り込み・表示中の合計
- スマートフォン向けの画面、日本円の整数入力

金額は各売上の合計金額として入力します。数量・税計算・商品マスターはありません。「今日」と「今月」は日本時間で画面を開いた時点を基準にします。日付をまたいだ際は再読み込みしてください。集計は全売上が対象で、一覧の絞り込みとは独立しています。

## データの保存とバックアップ

開発時の売上は `data/sales.sqlite3` に自動保存され、再起動後も残ります。Renderでは永続ディスク `/var/data` に保存します。無料プランや永続ディスクなしに変更すると、売上を保持できないため、この設定を維持してください。公開時の初期データは空です。開発用の売上は自動転送しません。

停止できる環境ではサーバーを停止してからDBファイルをコピーできます。稼働中のバックアップにはSQLiteのbackup APIを使用してください。バックアップには売上データが含まれるので、非公開の場所に保管してください。ディスクやサービスの削除前には必ずバックアップしてください。

```sh
.venv/bin/python manage.py backup /private/path/mcafe-backup.sqlite3
```

`DATABASE_PATH` に設定されたDB（未設定時は `data/sales.sqlite3`）をバックアップします。既存の出力ファイルは上書きしません。

## 検証

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/sales.test.mjs
```

Pythonテストは一時DBで認証・認証なしのアクセス拒否・ログアウト・CSRF・ログイン試行制限・HTTPS Cookie・売上の登録／編集／削除／永続化・入力検証を確認します。Node.js 18以上のテストは、集計・検索・日付範囲・日本時間の日付を確認します。アプリの実行にNode.jsは不要です。

任意のブラウザ検証は、PlaywrightとChromiumを利用できる環境で `python tests/browser_smoke.py` を実行します。一時DBとテスト専用ログイン情報を使い、実データには書き込みません。
