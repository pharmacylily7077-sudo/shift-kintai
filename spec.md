# 薬局向けシフト勤怠・個人給与シミュレータ＆有休管理Webアプリ システム仕様書

## 1. プロジェクト概要

### 1.1 背景と目的
従来のGAS（Google Apps Script）やスプレッドシート型システムで発生していたデータ整合性問題（1セルJSON限界による破損、ランダム架空打刻による労基法上のリスク等）を根本的に解消する。
本システムは、**Google Cloud Run 上で動作するセキュア・高速・堅牢なモダンWebアプリケーション**として新規構築し、スタッフ主導の「給与シミュレーション」「有休自己管理」「適正な実打刻」および管理者の「シフト・勤怠統括」「給与ソフト連携CSV出力」を実現する。

---

## 2. システム要件・技術スタック

### 2.1 技術スタック
- **バックエンド**: Python 3.11+ / FastAPI
- **データベース / ORM**: SQLite (SQLAlchemy 2.0)
  - 1行1レコードの正規化リレーショナルモデル。Cloud Runのコンテナ環境に対応（将来的なCloud SQL / PostgreSQLへの移行も同一ORM定義で容易）。
- **フロントエンド**: HTML5, Vanilla JavaScript (モダンFetch API / レスポンシブ設計), Tailwind CSS (CDN), Lucide Icons
  - スマートフォンでの片手打刻・個人情報閲覧、PCでの管理者シフト編成に対応。
- **認証・セキュリティ**:
  - パスワード: `bcrypt` (passlib) によるセキュアハッシュ
  - 認証方式: JWT (JSON Web Tokens) を利用したセッション/トークン認証
  - 認可制御: ロールベース（`admin` / `staff`）およびエンドポイントレベルの個人情報分離
- **インフラ・コンテナ**:
  - Docker (`python:3.11-slim` ベース)
  - Google Cloud Run (ポート8080対応、オートスケール)

---

## 3. データベース設計（テーブル定義）

### 3.1 `users`（ユーザー・スタッフ・管理者）
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, AutoIncrement | ユーザーID |
| `username` | String(50) | Unique, Not Null | ログイン用ID（例: staff01） |
| `password_hash` | String(255) | Not Null | bcryptハッシュ化パスワード |
| `full_name` | String(100) | Not Null | 氏名（例: 山田 花子） |
| `role` | String(20) | Not Null, Default='staff' | 権限 (`admin` / `staff`) |
| `wage_type` | String(20) | Not Null, Default='HOURLY' | 給与形態 (`HOURLY`: 時給 / `MONTHLY`: 月給) |
| `hourly_wage` | Integer | Default=0 | 時給/単価（個人入力・変更可） |
| `monthly_salary`| Integer | Default=0 | 基本月給（月給制の場合） |
| `paid_leave_granted` | Float | Default=0.0 | 今年度の有休付与日数（個人管理） |
| `paid_leave_carried` | Float | Default=0.0 | 前年度からの繰越日数（個人管理） |
| `paid_leave_base_date`| Date | Nullable | 有休基準日/付与日 |
| `is_active` | Boolean | Default=True | アカウント有効フラグ |
| `created_at` | DateTime | Default=now() | 作成日時 |
| `updated_at` | DateTime | OnUpdate=now() | 更新日時 |

### 3.2 `shifts`（シフトテーブル）
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, AutoIncrement | シフトID |
| `user_id` | Integer | FK(users.id), Not Null | 対象スタッフID |
| `date` | Date | Not Null, Index | シフト日 (YYYY-MM-DD) |
| `start_time` | Time | Nullable | 予定開始時刻 (例: 09:00) |
| `end_time` | Time | Nullable | 予定終了時刻 (例: 18:00) |
| `break_minutes` | Integer | Default=60 | 予定休憩時間（分） |
| `shift_type` | String(20) | Default='NORMAL' | 区分 (`NORMAL`: 通常出勤, `PAID_LEAVE`: 有休, `HOLIDAY`: 公休) |
| `note` | String(255) | Nullable | 備考 |

### 3.3 `time_records`（実打刻記録テーブル）
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, AutoIncrement | 打刻レコードID |
| `user_id` | Integer | FK(users.id), Not Null | 対象スタッフID |
| `date` | Date | Not Null, Index | 勤務日 (YYYY-MM-DD) |
| `clock_in` | DateTime | Nullable | 出勤打刻時刻 |
| `clock_out` | DateTime | Nullable | 退勤打刻時刻 |
| `break_start` | DateTime | Nullable | 休憩開始打刻時刻 |
| `break_end` | DateTime | Nullable | 休憩終了打刻時刻 |
| `total_break_minutes` | Integer | Default=0 | 実休憩時間（分） |
| `total_work_minutes` | Integer | Default=0 | 実労働時間（分） |
| `status` | String(20) | Default='WORKING' | 状態 (`WORKING`, `ON_BREAK`, `LEFT`, `NONE`) |
| `is_corrected` | Boolean | Default=False | 修正反映フラグ |
| `note` | String(255) | Nullable | 本人メモ（遅刻理由等） |

### 3.4 `correction_requests`（打刻修正申請テーブル）
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, AutoIncrement | 申請ID |
| `user_id` | Integer | FK(users.id), Not Null | 申請者ID |
| `time_record_id`| Integer | FK(time_records.id), Nullable | 対象打刻レコードID |
| `target_date` | Date | Not Null | 対象勤務日 |
| `requested_clock_in` | DateTime | Nullable | 修正希望 出勤時刻 |
| `requested_clock_out`| DateTime | Nullable | 修正希望 退勤時刻 |
| `requested_break_minutes` | Integer | Default=60 | 修正希望 休憩時間（分） |
| `reason` | Text | Not Null | 申請理由（打刻忘れ、機器トラブル等） |
| `status` | String(20) | Default='PENDING' | 承認状況 (`PENDING`, `APPROVED`, `REJECTED`) |
| `admin_comment` | String(255) | Nullable | 管理者コメント |
| `created_at` | DateTime | Default=now() | 申請日時 |

---

## 4. コア機能詳細仕様

### 4.1 スタッフ画面（個人マイページ・打刻）
1. **実打刻システム**:
   - 画面上に現在のステータス（未出勤 / 勤務中 / 休憩中 / 退勤済）をリアルタイム表示。
   - 「出勤」「休憩入」「休憩戻」「退勤」ボタン（直前状態に応じた二重打刻防止制御）。
2. **個人給与シミュレーション**:
   - **確定給与（当月概算）**: 実打刻実績（分単位）から時給換算でリアルタイム自動計算。
   - **月末着地見込み額**: 「当月確定額」＋「本日以降の予定シフト労働時間 × 設定時給」を合算。
   - **扶養枠（103万円・130万円）シミュレータ**: 年間ペースおよび残枠・残り許容稼働時間を表示。
3. **有給休暇自己管理**:
   - 付与日数・前年繰越日数を個人で入力・更新可能。
   - シフト「有休」実績と連動した「残日数」「消化日数」の自動計算。
   - 労基法「年5日取得義務」の進捗メーター（未達時の警告表示）。
4. **打刻修正申請**:
   - 打刻漏れや誤打刻時の日時・理由付き申請機能。

### 4.2 管理者画面（Adminダッシュボード）
1. **シフト作成・カレンダー管理**:
   - スタッフ全員のシフトカレンダー表示、作成、編集、一括展開。
2. **リアルタイム勤怠モニタリング**:
   - 当日の出退勤状況一覧、打刻乖離アラート。
3. **打刻修正申請の承認・却下**:
   - 申請一覧の審査、ワンクリック承認による勤怠レコード自動補正。
4. **給与ソフト連携「月次勤怠集計CSVエクスポート」**:
   - 対象月を指定し、freee/マネーフォワード/弥生等へインポート可能な標準CSVを出力。

---

## 5. セキュリティ・個人情報保護仕様

1. **APIレスポンスの個人データ分離（最重要）**:
   - `/api/me/...` はトークン内の `user_id` のデータのみを返却。
   - スタッフが他者の時給・給与・有休残日数を閲覧できるAPIは存在させない。
2. **管理者権限の厳格チェック**:
   - `/api/admin/...` へのアクセス時は `role == 'admin'` を強制。
3. **パスワード安全対策**:
   - `bcrypt` ハッシュ化によるストレッチング暗号化。

---

## 6. デプロイ仕様（Google Cloud Run）

- **ポート**: 環境変数 `PORT`（デフォルト 8080）でリッスン。
- **デプロイスクリプト (`deploy_cloud_run.sh`)**:
  - `gcloud run deploy` コマンドでソース直接ビルド＆恒久URL自動発行。

---

## 7. 追加機能仕様（フェーズ2：高度シフト編成＆印刷機能）

### 7.1 従業員ごとの雇用条件（固定勤務ルール）の事前登録
- テーブル `user_shift_preferences` または `users` カラム拡張:
  - 基本勤務曜日（例: [0, 1, 2, 4, 5] = 月火水金土）
  - 基本開始/終了時刻（例: 09:00 - 18:00）
  - 基本休憩時間（例: 60分）
  - 週所定勤務日数 / 月上限時間（扶養枠調整用）
  - スタッフ固有の識別カラー（例: エメラルド、パープル、アンバー、ブルー、ローズ等）

### 7.2 従業員からの「シフト希望（休み希望）」提出機能
- テーブル `shift_requests`:
  - `user_id`, `target_date`, `request_type` (`OFF`: 休み希望, `WORK`: 勤務希望, `PAID_LEAVE`: 有休希望), `preferred_start_time`, `preferred_end_time`, `reason`, `status` (`PENDING`, `APPROVED`, `REJECTED`)
- スタッフマイページのカレンダーから、来月などの日付をタップしてワンタッチで「休み希望」「有休希望」を申請可能。

### 7.3 1ヶ月分シフトの「ワンクリック一括自動作成」機能
- 管理者画面で「✨ 雇用条件から一括自動生成」を実行すると：
  - 対象月の全日について、スタッフの雇用条件（基本曜日）に基づきシフトを自動配置。
  - **重要**: スタッフから提出された「休み希望（OFF）」や「有休希望（PAID_LEAVE）」がある日は自動的に公休/有休として扱い、通常出勤を入れない。

### 7.4 従業員ごとの自動色分け＆名前常時表示
- カレンダー上のシフトバッジを、スタッフごとに異なる背景色・枠線で色分け（例: 佐藤さんは緑系、田中さんは紫系）。
- カレンダーのマス目に「佐藤」「田中」といったスタッフ名を大きくわかりやすく常時表示。

### 7.5 薬局貼り出し用「月間シフト表 印刷機能」
- 管理者画面に「🖨️ シフト表を印刷（A4横）」ボタンを設置。
- 印刷専用CSS（`@media print`）を適用し、ヘッダーや操作ボタン等の不要な要素を自動非表示にして、**A4横1枚に綺麗に収まる薬局掲示用シフト表**を出力（ブラウザの印刷プレビューからPDF保存や直接印刷が可能）。
