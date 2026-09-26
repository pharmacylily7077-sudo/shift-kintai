"""
shift_rules.py - リリー薬局 シフトルール判定モジュール
【現場の就業時間体系】
就業時間のパターンは「出勤」か「休日」のみ。
1. 日曜・祝日: 全員一斉休み
2. スタッフ固有の定休日 (fixed_off_weekdays): 休み
3. 土曜日: 出勤者全員「午前診 (AM: 9:00〜13:00)」
4. 木曜日: 出勤者全員「午前だけ (AM: 9:00〜13:00)」
5. その他出勤日 (月・火・水・金): 全員「全日 (FULL: 9:00〜19:00)」
"""
from datetime import date
from typing import Optional
import models
from holidays import is_sunday_or_holiday

def calculate_shift_type(user: models.User, d: date) -> Optional[models.ShiftType]:
    """
    指定されたスタッフと日付に対するシフト種別を判定して返す。
    休日の場合は None を返す。
    """
    # 1. 日曜・祝日は全員一斉休み
    if is_sunday_or_holiday(d):
        return None

    # 2. 定休日判定 (0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日)
    weekday_str = str(d.weekday())
    off_days = [x.strip() for x in (user.fixed_off_weekdays or "6").split(",")]
    if weekday_str in off_days:
        return None

    # 3. 土曜日は出勤者全員「午前診 (AM: 9:00〜13:00)」
    if d.weekday() == 5:
        return models.ShiftType.AM

    # 4. 木曜日は出勤者全員「午前だけ (AM: 9:00〜13:00)」
    if d.weekday() == 3:
        return models.ShiftType.AM

    # 5. その他の出勤日 (月・火・水・金) は全員「全日 (FULL: 9:00〜19:00)」
    return user.default_shift if user.default_shift else models.ShiftType.FULL

