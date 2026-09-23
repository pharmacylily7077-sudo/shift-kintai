"""
shift_rules.py - リリー薬局 シフトルール判定モジュール
1. 日曜・祝日: 全員一斉休み
2. スタッフ固有の定休日 (fixed_off_weekdays):
   - 三宅: 日曜(6)
   - 家田、寺内、山中、本間: 火曜(1)、日曜(6)
   - 小林: 木曜(3)、日曜(6)
3. 土曜日: 出勤スタッフ全員「午前診 (AM: 9:00〜13:00)」
4. 本間 まや: 木曜日は「午前診 (AM: 9:00〜13:00)」
5. 小林 彩乃: 火曜日は「午前診 (AM: 9:00〜13:00)」
6. その他: 各スタッフの通常シフト (default_shift)
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

    # 3. 土曜日は全員午前診 (AM)
    if d.weekday() == 5:
        return models.ShiftType.AM

    # 4. 本間は木曜日午前診 (AM)
    if user.username == "honma" and d.weekday() == 3:
        return models.ShiftType.AM

    # 5. 小林は火曜日は午前診 (AM)
    if user.username == "kobayashi" and d.weekday() == 1:
        return models.ShiftType.AM

    # 6. 通常シフト
    return user.default_shift
