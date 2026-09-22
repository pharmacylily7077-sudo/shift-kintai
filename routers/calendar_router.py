import calendar
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
import models
from holidays import get_holiday_name

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

SHIFT_LABELS = {
    "FULL": "全日",
    "AM": "午前診",
    "PM": "午後診",
    "FIRST": "前半",
    "SECOND": "後半",
    "OFF": "休み",
}

SHIFT_COLORS_FULL = {
    "PHARMACIST": "#16a34a",
    "CLERK": "#2563eb",
    "ASSISTANT": "#dc2626",
}
SHIFT_COLORS_PART = {
    "PHARMACIST": "#86efac",
    "CLERK": "#93c5fd",
    "ASSISTANT": "#fca5a5",
}


@router.get("/monthly")
def get_monthly_calendar(
    year: int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db)
):
    """公開シフトカレンダーデータ（給与情報なし）"""
    today = date.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    # 月の全日付
    _, days_in_month = calendar.monthrange(year, month)
    first_weekday = calendar.monthrange(year, month)[0]  # 0=月曜

    # 全スタッフ取得
    staff = db.query(models.User).filter(
        models.User.is_active == True
    ).order_by(models.User.position, models.User.id).all()

    # 月間シフト取得
    shifts = db.query(models.Shift).filter(
        models.Shift.date >= date(year, month, 1),
        models.Shift.date <= date(year, month, days_in_month)
    ).all()

    # 日付→{user_id: shift} のマップ
    shift_map = {}
    for s in shifts:
        d = s.date.day
        if d not in shift_map:
            shift_map[d] = {}
        shift_map[d][s.user_id] = s

    # スタッフ情報（色・ポジション）
    staff_info = []
    for u in staff:
        color = (
            SHIFT_COLORS_FULL[u.position.value]
            if u.employment_type == models.EmploymentType.FULLTIME
            else SHIFT_COLORS_PART[u.position.value]
        )
        staff_info.append({
            "id": u.id,
            "full_name": u.full_name,
            "position": u.position.value,
            "position_label": u.position_label,
            "employment_type": u.employment_type.value,
            "color": color,
            "is_admin": u.is_admin,
        })

    # 日付別データ
    days_data = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        weekday = d.weekday()  # 0=月, 6=日
        day_shifts = []

        for u in staff:
            s = shift_map.get(day, {}).get(u.id)
            if s:
                color = (
                    SHIFT_COLORS_FULL[u.position.value]
                    if u.employment_type == models.EmploymentType.FULLTIME
                    else SHIFT_COLORS_PART[u.position.value]
                )
                day_shifts.append({
                    "user_id": u.id,
                    "full_name": u.full_name,
                    "position": u.position.value,
                    "shift_type": s.shift_type.value,
                    "shift_label": s.shift_label,
                    "time_range": s.time_range,
                    "color": color,
                })

        holiday_name = get_holiday_name(d)
        is_holiday = holiday_name is not None

        days_data.append({
            "day": day,
            "weekday": weekday,  # 0=月〜6=日
            "weekday_label": ["月", "火", "水", "木", "金", "土", "日"][weekday],
            "is_sunday": weekday == 6,
            "is_saturday": weekday == 5,
            "is_holiday": is_holiday,
            "holiday_name": holiday_name,
            "is_today": d == today,
            "shifts": day_shifts,
        })

    return {
        "year": year,
        "month": month,
        "month_label": f"{year}年{month}月",
        "days_in_month": days_in_month,
        "first_weekday": first_weekday,
        "staff": staff_info,
        "days": days_data,
    }
