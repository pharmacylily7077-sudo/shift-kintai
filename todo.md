# 開発タスクリスト (todo.md)

薬局向けシフト勤怠・個人給与シミュレータ＆有休管理Webアプリの新規構築タスク一覧です。すべてのタスクが正常に完了しました。

---

## 1. プロジェクト初期設定・環境構築
- [x] `requirements.txt` の作成 (FastAPI, uvicorn, sqlalchemy, pydantic, bcrypt, pyjwt, python-multipart, jinja2 等)
- [x] 仮想環境の作成とパッケージインストール確認

## 2. データベース＆モデル設計 (`models.py`, `database.py`)
- [x] `database.py` の実装
  - [x] SQLAlchemy エンジン、SessionLocal、Base の定義
  - [x] 初期マスターデータ投入スクリプト (管理者 `admin`、テスト用スタッフアカウント2名、サンプルシフトデータ)
- [x] `models.py` の実装
  - [x] `User` モデル (username, password_hash, role, hourly_wage, paid_leave_granted, paid_leave_carried 等)
  - [x] `Shift` モデル (user_id, date, start_time, end_time, shift_type, note)
  - [x] `TimeRecord` モデル (user_id, date, clock_in, clock_out, break_start, break_end, total_work_minutes)
  - [x] `CorrectionRequest` モデル (user_id, time_record_id, requested_clock_in/out, reason, status)

## 3. 認証＆セキュリティモジュール (`auth.py`)
- [x] パスワードの bcrypt ハッシュ化 (`hash_password` / `verify_password`)
- [x] JWT 生成・検証ロジック (`create_access_token`, `get_token_from_request`)
- [x] 認可用 Depends ユーティリティ
  - [x] `get_current_user`: ログインユーザー取得（Cookie/Header対応）
  - [x] `get_current_admin`: 管理者権限チェック（staffアクセス時は 403 Forbidden）

## 4. バックエンドAPI実装 (`main.py`, `routers/`)
- [x] **認証 API**
  - [x] `POST /api/auth/login`: 認証とJWT発行 (HttpOnly Cookie 設定)
  - [x] `POST /api/auth/logout`: Cookie消去
  - [x] `GET /api/auth/me`: ログイン中ユーザー情報取得
- [x] **スタッフ専用 API (`/api/me/...`)** ※他人のデータアクセスを完全遮断
  - [x] `GET /api/me/dashboard`: 今日の打刻状態、当月確定給与概算、月末着地見込み、扶養枠進捗
  - [x] `POST /api/me/clock`: 出勤・退勤・休憩入・休憩戻の手動打刻
  - [x] `GET /api/me/shifts`: 自身のシフト一覧
  - [x] `PUT /api/me/settings`: 自身の時給/有休付与日数/繰越日数の更新
  - [x] `GET /api/me/paid-leave-summary`: 有休残日数、消化日数、年5日取得義務進捗
  - [x] `POST /api/me/correction-request`: 打刻修正申請の提出
- [x] **管理者専用 API (`/api/admin/...`)**
  - [x] `GET /api/admin/shifts` & `POST /api/admin/shifts`: シフト一覧取得・作成・更新
  - [x] `GET /api/admin/attendance/summary`: 全スタッフの出勤状況・打刻漏れモニタリング
  - [x] `GET /api/admin/correction-requests`: 修正申請一覧取得
  - [x] `POST /api/admin/correction-requests/{id}/review`: 修正申請の承認・却下（承認時は実打刻に自動反映）
  - [x] `GET /api/admin/export-csv`: 給与ソフト連携用「月次勤怠集計CSV」出力

## 5. フロントエンドUI実装 (`templates/`, `static/`)
- [x] `templates/base.html`: 薬局らしい清潔感のあるデザインベース（Tailwind CSS, レスポンシブ対応, PWAメタタグ）
- [x] `templates/login.html`: ログイン画面（ワンクリック簡単テスト入力機能付き）
- [x] `templates/index.html` (スタッフマイページ):
  - [x] 直感的な大型打刻ボタン（出退勤・休憩の状態遷移）
  - [x] 個人給与シミュレータ（確定額、着地見込み、扶養枠メーター）
  - [x] 有休自己管理パネル（付与・繰越・残日数・年5日取得義務アラート）
  - [x] 自身のシフト・勤怠カレンダーおよび打刻修正申請モーダル
- [x] `templates/admin.html` (管理者ポータル):
  - [x] スタッフ全体の当日の勤怠ステータス一覧
  - [x] 月間シフト管理カレンダー
  - [x] 勤怠修正申請の承認・却下パネル
  - [x] CSVエクスポートUI
- [x] `static/js/app.js` & `static/js/admin.js` & `static/css/style.css`: フロントエンドのインタラクション実装

## 6. Docker & Google Cloud Run デプロイ設定
- [x] `Dockerfile` (Python 3.11-slim, ポート8080対応)
- [x] `.dockerignore` / `.gcloudignore`
- [x] `deploy_cloud_run.sh` (ターミナル1発でCloud RunへデプロイしてURLを発行するスクリプト)

## 7. 動作検証＆テスト
- [x] ローカル起動テスト (`uvicorn main:app --reload`)
- [x] 打刻フロー動作確認（出勤→休憩入→休憩戻→退勤）
- [x] 給与シミュレーション計算精度確認（実働分数 × 時給）
- [x] 扶養枠メーターおよび有休年5日取得アラート表示確認
- [x] 管理者側CSVエクスポートのフォーマット確認 (UTF-8 BOM付き)
- [x] スタッフ権限による他者情報閲覧不可のセキュリティテスト
- [x] 全6項目の自動テスト（pytest）完全通過

---

## 8. フェーズ2：高度シフト編成＆印刷機能（次回実装タスク）
- [ ] **1. 雇用条件・基本パターン管理**
  - [ ] `User` モデルに雇用条件カラム（基本曜日、基本時間、スタッフ別カラー等）または `WorkCondition` モデルの追加
  - [ ] 管理者画面に「スタッフ雇用条件設定」モーダル/パネル追加
- [ ] **2. 従業員のシフト希望（休み希望）提出機能**
  - [ ] `ShiftRequest` モデルの作成 (`user_id`, `date`, `type`, `reason`, `status`)
  - [ ] スタッフマイページからカレンダータップで「休み希望提出」できるUI・API
  - [ ] 管理者画面での希望シフト一覧表示と承認
- [ ] **3. 1ヶ月分の一括シフト自動生成ロジック**
  - [ ] 管理者画面に「✨ 雇用条件から一括自動生成」ボタン設置
  - [ ] 雇用条件に基づき、かつスタッフの希望休（OFF/有休）を自動スキップして1ヶ月分を一括生成するAPI
- [ ] **4. 従業員ごとの色分け＆名前常時表示**
  - [ ] カレンダーマス内のシフトバッジをスタッフごとに固有カラー（緑、紫、青、橙など）で自動色分け
  - [ ] スタッフ名がマス目で大きく目立つデザインにブラッシュアップ
- [ ] **5. 月間シフト表 印刷機能（A4横掲示用）**
  - [ ] 管理者画面に「🖨️ 印刷」ボタンを設置
  - [ ] `@media print` によるA4横に美しく収まる薬局掲示用プリントスタイルの実装
