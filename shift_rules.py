"""
shift_rules.py - リリー薬局 シフトルール判定モジュール
【現場の就業パターン】
- 全日 (FULL): 9:00〜19:00 (休憩60分)
- 前半 (FIRST): 9:00〜18:00 (休憩60分)
- 後半 (SECOND): 10:00〜19:00 (休憩60分)
- 午前診 (AM): 9:00〜13:00 (休憩なし)
- 午後診 (PM): 15:00〜19:00 (休憩なし)

【曜日ルール】
1. 日曜・祝日: 休局（全員一斉休み）
2. スタッフ固有の定休日 (fixed_off_weekdays):
   - 三宅: 日曜(6)
   - 家田、寺内、山中、本間: 火曜(1)、日曜(6)
   - 小林: 木曜(3)、日曜(6)
3. 土曜日: 出勤者全員「午前診 (AM: 9:00〜13:00)」
4. 木曜日: 「午前と全日」
   - 本間 まや: 午前診 (AM: 9:00〜13:00)
   - 三宅・家田・寺内・山中: 全日 (FULL: 9:00〜19:00)
   - 小林: 定休日
5. 火曜日: 「前半と全日」
   - 小林 彩乃: 前半 (FIRST: 9:00〜18:00)
   - 三宅 智之: 全日 (FULL: 9:00〜19:00)
   - 家田・寺内・山中・本間: 定休日
6. その他の出勤日 (月・水・金): 各スタッフの個別基本シフト (default_shift)
   - 小林 彩乃: 後半 (SECOND: 10:00〜19:00 / 休憩60分)
   - 本間 まや: 前半 (FIRST: 9:00〜18:00 / 休憩60分)
   - 三宅・家田・寺内・山中: 全日 (FULL: 9:00〜19:00 / 休憩60分)
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

    # 4. 木曜日は「午前と全日」: 本間まや は「午前診 (AM: 9:00〜13:00)」
    if user.username == "honma" and d.weekday() == 3:
        return models.ShiftType.AM

    # 5. 火曜日は「前半と全日」: 小林 彩乃 は「前半 (FIRST: 9:00〜18:00)」
    if user.username == "kobayashi" and d.weekday() == 1:
        return models.ShiftType.FIRST

    # 6. その他の出勤日 (月・水・金など通常出勤日) は各スタッフの基本シフト
    # (小林: 後半 10:00〜19:00 / 本間: 前半 9:00〜18:00 / 三宅・家田・寺内・山中: 全日 9:00〜19:00)
    return user.default_shift if user.default_shift else models.ShiftType.FULL


