# アーキテクチャ設計書 (ARCHITECTURE.md)

## 技術スタック

| 層 | 技術 | バージョン |
|---|---|---|
| バックエンド | Python / FastAPI | 3.11+ / 0.115.x |
| ORM | SQLAlchemy | 2.0.x |
| バリデーション | Pydantic | 2.x |
| 認証 | PyJWT + bcrypt | 2.8.x / 4.x |
| DB（ローカル） | SQLite WALモード | — |
| DB（本番） | PostgreSQL | 15+ |
| テンプレート | Jinja2 | 3.1.x |
| フロントエンド | HTML5 + Tailwind CSS CDN + Vanilla JS | — |
| アイコン | Lucide Icons CDN | — |
| アニメーション | CSS Transitions / Web Animations API | — |
| サーバー | Uvicorn（開発）/ Gunicorn（本番） | — |

---

## ディレクトリ構成

```
v2/
├── main.py                  # FastAPIアプリ起動・ルーター登録
├── database.py              # DB接続（SQLite/PostgreSQL自動切替）
├── models.py                # SQLAlchemyモデル
├── schemas.py               # Pydanticスキーマ
├── auth.py                  # JWT・パスワードハッシュ
├── seed.py                  # 初期スタッフデータ投入
├── SPEC.md                  # 機能仕様書
├── ARCHITECTURE.md          # 本ファイル
├── TODO.md                  # タスクリスト
├── AGENT_RULES.md           # AI行動規律
├── PROMPT_TEMPLATE.md       # AI指示テンプレート
├── auto_todo_runner.py      # 自動検証・Gitコミット・リミッター
├── setup.sh                 # 環境一発初期化
├── requirements.txt
├── Procfile                 # Render用
├── render.yaml              # Render設定
├── routers/
│   ├── auth.py              # /api/auth/login, /logout
│   ├── calendar.py          # /api/calendar （公開シフト）
│   ├── me.py                # /api/me/* （個人マイルーム）
│   └── admin.py             # /api/admin/* （管理者）
├── templates/
│   ├── base.html            # 共通ベース（Tailwind・Lucide読込）
│   ├── login.html           # 三重ロックログイン
│   ├── calendar.html        # 公開シフトカレンダー
│   ├── myroom.html          # マイルーム（ダッシュボード）
│   └── admin.html           # 管理者ダッシュボード
├── static/
│   ├── css/style.css        # カスタムCSS（印刷用含む）
│   └── js/
│       ├── calendar.js      # カレンダーロジック
│       ├── myroom.js        # マイルームロジック
│       └── admin.js         # 管理者ロジック
└── tests/
    └── test_app.py          # pytest テスト
```

---

## データモデル

### User
```
id, full_name, position (PHARMACIST/CLERK/ASSISTANT),
employment_type (FULLTIME/PARTTIME),
default_shift (FULL/AM/PM/FIRST/SECOND),
username (auto: position_name e.g. pharmacist_miyake),
password_hash, is_admin, is_active,
theme_color, theme_bg, widget_order,
hourly_wage (自己入力・暗号化保存), paid_leave_remaining (自己入力),
created_at
```

### Shift
```
id, user_id, date, shift_type (FULL/AM/PM/FIRST/SECOND/OFF),
note, created_at
```

### TimeRecord（自己申告勤怠）
```
id, user_id, date,
clock_in, clock_out, break_start, break_end,
status (NONE/WORKING/BREAK/DONE),
created_at
```

### PersonalSchedule
```
id, user_id, date, title, category (WORK/PRIVATE/HEALTH/BUDGET),
note, health_status (GOOD/OK/TIRED),
amount (家計簿用), is_income (収入/支出フラグ),
created_at
```

### LeaveRequest
```
id, user_id, date, request_type (URGENT/ADVANCE),
leave_type (OFF/PAID_LEAVE), reason,
status (PENDING/APPROVED/REJECTED),
admin_note, created_at
```

### Message
```
id, from_user_id, to_user_id, content,
is_read, created_at
```

---

## 命名規則

- ファイル名: `snake_case.py`
- クラス名: `PascalCase`
- 関数名: `snake_case`
- APIエンドポイント: `/api/{router}/{action}` (kebab-case)
- DBカラム: `snake_case`
- JSファイル内関数: `camelCase`
- CSSクラス: Tailwindのみ使用（カスタムは最小限）

---

## 認証フロー

```
ログイン画面
  → STEP1: ポジション選択
  → STEP2: 名前選択（GET /api/auth/staff-list?position=PHARMACIST）
  → STEP3: パスワード入力
  → POST /api/auth/login → JWT発行 → HttpOnly Cookie設定
  → role=admin → /admin
  → role=staff → /me
```

---

## 印刷CSS方針

```css
@media print {
  /* 非表示: ナビ・ボタン・URL・ヘッダー */
  /* 表示: カレンダー本体のみ */
  /* 色: color-adjust: exact で色保持 */
  /* サイズ: A4横（297mm×210mm） */
}
```
