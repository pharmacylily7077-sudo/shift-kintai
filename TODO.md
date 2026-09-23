# タスク一覧

- [x] 1. スタッフ6名のフルネーム・固有評価カラーのモデル・シード・認証反映
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_staff_colors.py`

- [x] 2. マイページのフレンチ手帳デザイン・24の英語感謝メッセージ配信・カラーパレット着せ替え機能の実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_myroom_french.py`

- [ ] 3. 休みと金の自己責任カード（有休管理・給与残業速報）および打刻機能の実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_vacation_and_payroll.py`

- [ ] 4. 共通シフトカレンダーの清潔な白ベース化・評価カラーバッジ・A4横印刷レイアウトの実装
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_calendar_view.py`

- [ ] 5. 「正社員」「パート」表記の完全排除および総合自動テストの全件通過
  - 検証: `PYTHONPATH=. ./venv/bin/pytest tests/test_no_discriminatory_labels.py tests/test_app.py`
