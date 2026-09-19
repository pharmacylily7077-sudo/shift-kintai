# システムアーキテクチャ設計書 (ARCHITECTURE.md)

## 1. ディレクトリ構成

```text
shift-kintai/
├── main.py                  # アプリケーション初期化、ルートルーティング、PWA提供
├── database.py              # DB接続設定（PostgreSQL / SQLite WALモード自動切替）
├── models.py                # SQLAlchemy ORMデータモデル定義
├── schemas.py               # Pydanticバリデーションスキーマ定義
├── auth.py                  # パスワードハッシュ(bcrypt)、JWT生成・検証、認証ミドルウェア
├── seed.py                  # 初期マスターデータ投入スクリプト（三宅様アカウント初期化）
├── requirements.txt         # 依存Pythonライブラリ定義
├── render.yaml              # Renderクラウドインフラ構成設定
├── SPEC.md                  # システム仕様書
├── ARCHITECTURE.md          # アーキテクチャ設計書（本ドキュメント）
├── TODO.md                  # タスク進捗管理表
│
├── routers/                 # APIルーター層
│   ├── auth.py              # 認証関連API (/api/auth/login, /logout, /me)
│   ├── staff.py             # スタッフ向けAPI (打刻、シフト照会、希望申請、給与概算)
│   └── admin.py             # 管理者向けAPI (シフト編成、ユーザー管理、リセット、ZIP、LINE)
│
├── templates/               # Jinja2 HTMLテンプレート
│   ├── base.html            # 共通レイアウト、ヘッダー、トースト通知、PWAメタタグ
│   ├── index.html           # スタッフスマホマイページ（超特大出退勤ボタン）
│   ├── login.html           # ログイン画面（動的登録中アカウント一覧付き）
│   └── admin.html           # 管理者ポータル（3大導線、カレンダー、印刷、各種モーダル）
│
├── static/                  # 静的アセット
│   ├── css/
│   │   └── style.css        # カスタムスタイル、A4印刷用CSSプリントメディアクエリ
│   ├── js/
│   │   ├── app.js           # スタッフ画面クライアントロジック（リアルタイム時計、打刻通信）
│   │   └── admin.js         # 管理者画面クライアントロジック（シフト・給与・有休・PW・リセット）
│   ├── icons/               # PWA用アプリアイコン (icon-192.png, icon-512.png)
│   ├── manifest.json        # PWAマニフェスト定義ファイル
│   └── service-worker.js    # PWAサービスワーカー（オフライン制御）
│
└── tests/                   # 自動テストスイート
    ├── __init__.py
    └── test_app.py          # pytest単体・結合テスト（全80件超、100%パス）
```

---

## 2. 使用ライブラリとそのバージョン

本プロジェクトの主要依存関係（`requirements.txt`）：

| ライブラリ名 | バージョン範囲 / 指定 | 用途・役割 |
| :--- | :--- | :--- |
| **FastAPI** | `>=0.110.0,<0.116.0` | 非同期対応・高パフォーマンスWeb APIフレームワーク |
| **Uvicorn** | `>=0.28.0,<0.32.0` | ASGIサーバー（本番・開発時のWebサーバーエンジン） |
| **SQLAlchemy** | `>=2.0.25,<2.1.0` | ORM（リレーショナルデータベース操作・トランザクション管理） |
| **Pydantic** | `>=2.6.0,<2.10.0` | APIリクエスト/レスポンスの型定義・厳格バリデーション |
| **bcrypt** | `>=4.0.1,<4.3.0` | パスワードの安全なソルト付与・不可逆ハッシュ化 |
| **pyjwt[crypto]** | `>=2.8.0,<2.10.0` | JSON Web Token (JWT) によるステートレス認証トークン発行・検証 |
| **python-multipart** | `>=0.0.9` | フォームデータ・ファイルアップロード解析 |
| **Jinja2** | `>=3.1.3` | サーバーサイドHTMLテンプレートレンダリング |
| **psycopg2-binary** | `>=2.9.9` | Render本番クラウド（PostgreSQL）接続用DBドライバ |
| **Gunicorn** | `>=21.2.0` | 本番環境用WSGI/ASGIプロセスマネージャー |
| **pytest** | `>=8.0.0` | 自動テスト実行フレームワーク |
| **HTTPX** | `>=0.27.0` | FastAPI TestClient用非同期・同期HTTPクライアント |

---

## 3. 命名規則・コーディング規約

### 3.1 Python (バックエンド)
- **ファイル名**: スネークケース（例: `admin.py`, `test_app.py`）
- **クラス名**: パスカルケース（例: `User`, `ShiftRequest`, `UserPasswordReset`）
- **関数名・変数名**: スネークケース（例: `get_attendance_summary`, `user_id`）
- **定数**: 大文字スネークケース（例: `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`）
- **DBテーブル名**: 小文字複数形スネークケース（例: `users`, `shifts`, `time_records`）
- **DBカラム名**: 小文字スネークケース（例: `is_active`, `paid_leave_granted`）

### 3.2 JavaScript / CSS (フロントエンド)
- **JS関数名・変数名**: キャメルケース（例: `loadAdminShifts`, `renderStaffManagementCards`）
- **HTML Element ID**: ケバブケース（例: `section-staff`, `condition-modal`, `new-reset-password`）
- **CSSクラス**: Tailwind CSSユーティリティクラスを優先使用、カスタムはケバブケース（例: `print-table`）

### 3.3 RESTful APIエンドポイント
- **コレクションURI**: 複数形名詞（例: `/api/admin/users`, `/api/admin/shifts`）
- **個別リソースURI**: ID指定（例: `/api/admin/users/{user_id}`）
- **HTTPメソッド**:
  - `GET`: リソース取得
  - `POST`: 新規作成・一括アクション（例: `/api/admin/reset-all`, `/api/auth/login`）
  - `PUT`: リソース更新（例: `/api/admin/users/{user_id}/condition`）
  - `DELETE`: リソース削除（例: `/api/admin/users/{user_id}`）

---

## 4. データフローと永続化アーキテクチャ

1. **マルチDB対応**:
   - `DATABASE_URL` 環境変数が存在する場合は PostgreSQL に接続（Render本番）。
   - 環境変数が未設定の場合は ローカルSQLite（`kintai.db`）に接続。SQLite時はWALジャーナルモードと即時同期（NORMAL）を自動有効化。
2. **二重認証ハンドリング**:
   - Webブラウザ利用時は `HttpOnly; SameSite=Lax` Cookie を利用（XSS対策・リロード時の認証維持）。
   - APIクライアント・スクリプト利用時は `Authorization: Bearer <token>` ヘッダーをサポート。
3. **カスケード完全整合性**:
   - スタッフ削除時は、関連する全シフト（`shifts`）、打刻（`time_records`）、申請（`shift_requests`, `correction_requests`）がリレーション定義または専用クリーンアップ処理によって矛盾なく即時一括処理される。
