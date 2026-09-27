"""
tests/test_staff_individual_shifts.py
スタッフ個別シフト（小林彩乃の後半・火曜AM、本間まやの前半・木曜AM、土曜全員AM、木曜全員AM）の完全保持検証
"""
import pytest
from datetime import date
from database import SessionLocal
import models
from shift_rules import calculate_shift_type

def test_all_staff_shift_spec_integrity():
    """スタッフ6名の確定シフト仕様が100%崩れていないことを厳格に検証"""
    db = SessionLocal()
    try:
        users = {u.username: u for u in db.query(models.User).all()}

        # 1. 各スタッフの default_shift
        assert users["miyake"].default_shift == models.ShiftType.FULL
        assert users["ieda"].default_shift == models.ShiftType.FULL
        assert users["terauchi"].default_shift == models.ShiftType.FULL
        assert users["yamanaka"].default_shift == models.ShiftType.FULL
        assert users["kobayashi"].default_shift == models.ShiftType.SECOND # 後半 (10:00〜19:00)
        assert users["honma"].default_shift == models.ShiftType.FIRST      # 前半 (9:00〜18:00)

        # 2. 小林彩乃さんの勤務判定
        # 火曜日: 前半 (FIRST: 9:00〜18:00) ※火曜は前半と全日
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 1)) == models.ShiftType.FIRST
        # 水曜日: 後半 (SECOND: 10:00〜19:00)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 2)) == models.ShiftType.SECOND
        # 木曜日: 定休日 (None)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 3)) is None
        # 金曜日: 後半 (SECOND: 10:00〜19:00)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 4)) == models.ShiftType.SECOND
        # 土曜日: 午前診 (AM: 9:00〜13:00)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 5)) == models.ShiftType.AM
        # 日曜日: 定休日 (None)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 6)) is None
        # 月曜日: 後半 (SECOND: 10:00〜19:00)
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 7)) == models.ShiftType.SECOND

        # 3. 本間まやさんの勤務判定
        # 火曜日: 定休日 (None)
        assert calculate_shift_type(users["honma"], date(2026, 9, 1)) is None
        # 水曜日: 前半 (FIRST: 9:00〜18:00)
        assert calculate_shift_type(users["honma"], date(2026, 9, 2)) == models.ShiftType.FIRST
        # 木曜日: 午前診 (AM: 9:00〜13:00) ※木曜は午前と全日
        assert calculate_shift_type(users["honma"], date(2026, 9, 3)) == models.ShiftType.AM
        # 金曜日: 前半 (FIRST: 9:00〜18:00)
        assert calculate_shift_type(users["honma"], date(2026, 9, 4)) == models.ShiftType.FIRST
        # 土曜日: 午前診 (AM: 9:00〜13:00)
        assert calculate_shift_type(users["honma"], date(2026, 9, 5)) == models.ShiftType.AM
        # 日曜日: 定休日 (None)
        assert calculate_shift_type(users["honma"], date(2026, 9, 6)) is None
        # 月曜日: 前半 (FIRST: 9:00〜18:00)
        assert calculate_shift_type(users["honma"], date(2026, 9, 7)) == models.ShiftType.FIRST

        # 4. 木曜日の「午前と全日」判定
        assert calculate_shift_type(users["miyake"], date(2026, 9, 3)) == models.ShiftType.FULL # 全日
        assert calculate_shift_type(users["ieda"], date(2026, 9, 3)) == models.ShiftType.FULL   # 全日
        assert calculate_shift_type(users["terauchi"], date(2026, 9, 3)) == models.ShiftType.FULL # 全日
        assert calculate_shift_type(users["yamanaka"], date(2026, 9, 3)) == models.ShiftType.FULL # 全日
        assert calculate_shift_type(users["honma"], date(2026, 9, 3)) == models.ShiftType.AM    # 午前診
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 3)) is None              # 木曜定休

        # 4-2. 火曜日の「前半と全日」判定
        assert calculate_shift_type(users["miyake"], date(2026, 9, 1)) == models.ShiftType.FULL   # 全日
        assert calculate_shift_type(users["kobayashi"], date(2026, 9, 1)) == models.ShiftType.FIRST # 前半
        assert calculate_shift_type(users["ieda"], date(2026, 9, 1)) is None                    # 火曜定休
        assert calculate_shift_type(users["terauchi"], date(2026, 9, 1)) is None                # 火曜定休
        assert calculate_shift_type(users["yamanaka"], date(2026, 9, 1)) is None                # 火曜定休
        assert calculate_shift_type(users["honma"], date(2026, 9, 1)) is None                   # 火曜定休

        # 5. 土曜日の出勤者全員午前診判定
        for u in users.values():
            assert calculate_shift_type(u, date(2026, 9, 5)) == models.ShiftType.AM

        # 6. 祝日の休局（全員休み）判定
        for hol in [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]:
            for u in users.values():
                assert calculate_shift_type(u, hol) is None

    finally:
        db.close()
