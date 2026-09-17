# プロジェクト引き継ぎ書 (handoff.md)

## 1. プロジェクト概要 & 現状
薬局向けシフト勤怠・個人給与シミュレータ＆有休管理Webアプリです。
フェーズ1（コア勤怠・給与シミュレーション・7列月間グリッドカレンダー・CSV出力・自動テスト）は完全実装＆稼働検証済みです。
全自動テスト（pytest）6項目が通過しており、FastAPI + SQLite + Tailwind CSS / Vanilla JS で安定稼働しています。

- **バックエンド**: `main.py`, `database.py`, `models.py`, `schemas.py`, `auth.py`, `routers/` (`auth.py`, `staff.py`, `admin.py`)
- **フロントエンド**: `templates/` (`base.html`, `login.html`, `index.html`, `admin.html`), `static/` (`css/style.css`, `js/app.js`, `js/admin.js`)
- **テスト**: `tests/test_app.py`（実行コマンド: `PYTHONPATH=. ./venv/bin/pytest`）
- **初期データ**: `seed.py`（管理者: admin/admin123, スタッフ1: staff01/staff123, スタッフ2: staff02/staff123）

---

## 2. フェーズ2 実装要件 & 確定設計

ユーザー様はプログラミング初心者のため、**選択肢を迫らず、最も壊れにくく堅牢で使いやすい標準仕様**で実装を進めること。

### 要件と設計一覧:
1. **雇用条件管理（固定勤務ルール）**:
   - `User` モデルにカラムを追加（SQLiteマイグレーション事故を防止し最も壊れにくい設計）:
     - `work_days` (文字列例: `"0,1,2,4,5"` ※0=月〜6=日)
     - `default_start_time` (Time, 例: 09:00)
     - `default_end_time` (Time, 例: 18:00)
     - `default_break_minutes` (Integer, 例: 60)
     - `color` (文字列例: `"#059669"`, スタッフ固定カラー)
   - 管理者ポータルに「👥 雇用条件設定」モーダルを設置。
   - API: `PUT /api/admin/users/{user_id}/condition`
2. **従業員のシフト希望（休み希望）提出機能**:
   - `ShiftRequest` モデルの作成 (`id`, `user_id`, `date`, `request_type` ("OFF"|"PAID_LEAVE"), `reason`, `status` ("PENDING"|"APPROVED"|"REJECTED"), `admin_comment`, `created_at`)
   - スタッフマイページのカレンダー操作部に「🏖️ 休み希望提出」ボタンを設置（希望日・区分・理由を入力）。
   - カレンダーマス目にも「希望休(申請中)」「希望休(承認済)」を表示。
   - 管理者画面に「シフト希望審査パネル」を設置（承認/却下ボタン）。
   - API:
     - スタッフ: `POST /api/me/shift-requests`, `GET /api/me/shift-requests`, `DELETE /api/me/shift-requests/{id}`
     - 管理者: `GET /api/admin/shift-requests`, `POST /api/admin/shift-requests/{id}/review`
3. **1ヶ月分の一括シフト自動生成機能**:
   - 管理者画面に「✨ 一括自動生成」ボタンを設置。
   - 雇用条件（基本曜日・時間）に基づき、承認された希望休（OFF）は自動スキップ、有休希望（PAID_LEAVE）は有休シフトとして1ヶ月分を一括生成。
   - API: `POST /api/admin/shifts/auto-generate`
4. **従業員ごとの色分け＆名前のわかりやすい常時表示**:
   - カレンダーマス内のシフトバッジを、スタッフ固定色（エメラルド、パープル、インディゴ、アンバー等）で描画。
   - マス目内で名前を大きく太字で常時表示。
5. **薬局貼り出し用「月間シフト表 印刷機能」**:
   - 管理者画面に「🖨️ シフト表印刷」ボタンを設置（`window.print()`）。
   - `@media print` CSS によるA4横向き1枚（`@page { size: A4 landscape; margin: 8mm; }`）専用スタイル。
   - ヘッダー・操作ボタン・モニタリング表・サイドパネル等は自動非表示（`.no-print`）。

---

## 3. 次のチャットでの実施手順

1. **モデル & スキーマ更新**:
   - `models.py`: `User` に雇用条件・カラーカラム追加、`ShiftRequest` モデル追加
   - `schemas.py`: 雇用条件更新用スキーマ、シフト希望スキーマ、自動生成リクエストスキーマ
2. **ルーター（API）実装**:
   - `routers/admin.py`: 雇用条件更新、シフト希望取得・審査、一括自動生成API
   - `routers/staff.py`: シフト希望提出・取得・取消API、シフトカレンダーに希望休情報統合
3. **フロントエンド実装**:
   - `templates/admin.html` & `static/js/admin.js`: 一括自動生成ボタン、雇用条件モーダル、希望休審査パネル、印刷ボタン、スタッフ色分け描画
   - `templates/index.html` & `static/js/app.js`: 休み希望提出モーダル、カレンダーへの希望休表示
   - `static/css/style.css`: A4横印刷用 `@media print` スタイル定義
4. **初期データ & テスト**:
   - `seed.py`: スタッフの雇用条件と希望休の初期データ追加
   - `tests/test_app.py`: フェーズ2のテスト追加と実行（`PYTHONPATH=. ./venv/bin/pytest` で全テスト通過確認）

---

## 4. 新しいチャット用 貼り付けプロンプト

```markdown
handoff.md を読み込んで、「フェーズ2：高度シフト編成＆印刷機能」の実装を一気に完了させてください。
選択肢は不要です。handoff.md に記載された最も壊れにくい標準仕様に沿って実装し、自動テスト（PYTHONPATH=. ./venv/bin/pytest）がすべてパスすることを確認してください。
```

