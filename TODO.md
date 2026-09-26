# タスク一覧

- [x] 1. スタッフ6名のフルネーム・固有評価カラーのモデル・シード・認証反映
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_staff_colors.py`

- [x] 2. マイページのフレンチ手帳デザイン・24の英語感謝メッセージ配信・カラーパレット着せ替え機能の実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_myroom_french.py`

- [x] 3. 休みと金の自己責任カード（有休管理・給与残業速報）および打刻機能の実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_vacation_and_payroll.py`

- [x] 4. 共通シフトカレンダーの清潔な白ベース化・評価カラーバッジ・A4横印刷レイアウトの実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_calendar_view.py`

- [x] 5. 「正社員」「パート」表記の完全排除および総合自動テストの全件通過
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_no_discriminatory_labels.py tests/test_app.py`

- [x] 6. 雇用形態ごとの勤務時間調節・詳細設定機能（シフト区分・定休曜日・時給・有休残日数）
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_conditions_and_pdf.py`

- [x] 7. シフト表のワンクリックPDF出力機能（A4横向き高解像度ダウンロード）＆ LINE共有・ZIP保存・有休5日義務アラート
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_conditions_and_pdf.py`

- [x] 8. 小林・本間専用リアル秒単位ゆらぎ一括打刻支援 ＆ タイムカード（出勤簿）PDF・印刷・CSV出力機能（HH:MM:SS形式・完全ログ非保持）
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_timecard_batch_fill.py`

- [x] 9. マイページ週間スケジュールのリアル祝日・個人定休動的同期（モック静的水曜公休バグの完全根絶）
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_myroom_french.py`

- [x] 10. 就業時間パターンのシンプル化（出勤か休日のみ：木曜午前・土曜午前・平日全日）
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_app.py`



