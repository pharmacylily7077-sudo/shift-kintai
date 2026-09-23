import calendar
from datetime import date, datetime, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
from auth import get_current_user

router = APIRouter(prefix="/api/me", tags=["me"])


# 恋人に伝えるかのような24の感謝・温もりフレーズ（お説教・ダサい標語を完全排除）
GENTLE_THOUGHTS = [
    "I am grateful for you.",
    "Thank you for being in my life.",
    "Appreciate every moment.",
    "You make my world brighter.",
    "I couldn’t have done it without you.",
    "A grateful heart is a happy heart.",
    "Thank you for your kindness.",
    "Every day is a gift.",
    "Gratitude changes everything.",
    "Thank you for believing in me.",
    "I am so lucky to have you.",
    "Wake up with gratitude.",
    "You showed up when it mattered.",
    "Thank you for your support.",
    "Enough is a feast.",
    "Your help means the world to me.",
    "Thank you for being you.",
    "Joy is in the little things.",
    "I appreciate you.",
    "Kindness is never forgotten.",
    "Thank you for the memories.",
    "Grateful for the journey.",
    "Thank you, from the bottom of my heart.",
    "You make a difference every single day."
]

# --- Pydantic リクエストモデル ---

class WageUpdateRequest(BaseModel):
    hourly_wage: int


class PaidLeaveUpdateRequest(BaseModel):
    paid_leave_remaining: float


class ClockActionRequest(BaseModel):
    action: str  # IN / BREAK_START / BREAK_END / OUT


class HealthRecordRequest(BaseModel):
    date: str  # YYYY-MM-DD
    health_status: str  # GOOD / OK / TIRED
    note: Optional[str] = ""


class BudgetRecordRequest(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    amount: int
    is_income: bool  # True: 収入 / False: 支出
    note: Optional[str] = ""


class ScheduleRecordRequest(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    note: Optional[str] = ""


class LeaveApplyRequest(BaseModel):
    date: str  # YYYY-MM-DD
    request_type: str = "ADVANCE"  # URGENT / ADVANCE
    leave_type: str = "OFF"  # OFF / PAID_LEAVE
    reason: Optional[str] = ""


class ThemeUpdateRequest(BaseModel):
    theme_color: str
    theme_bg: str


# --- API エンドポイント ---

@router.get("/dashboard")
def get_my_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    マイルーム全体ダッシュボード情報（優先順位順）:
    1. 給与シミュレーター & 本日のシフト
    2. 有休管理
    3. 体調管理
    4. 家計簿サマリー
    5. 個別お知らせメッセージ
    """
    today = date.today()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    start_of_month = date(today.year, today.month, 1)
    end_of_month = date(today.year, today.month, days_in_month)

    # 1. 本日のシフト
    today_shift = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date == today
    ).first()

    # 2. 本日の打刻状況
    today_record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date == today
    ).first()

    clock_status = today_record.status.value if today_record else "NONE"
    clock_in_str = today_record.clock_in.strftime("%H:%M") if today_record and today_record.clock_in else None
    clock_out_str = today_record.clock_out.strftime("%H:%M") if today_record and today_record.clock_out else None

    # 3. 当月の出勤実績と労働時間計算（給与シミュレーター用）
    month_records = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date >= start_of_month,
        models.TimeRecord.date <= end_of_month
    ).all()

    total_work_minutes = sum(r.work_minutes for r in month_records)
    worked_days_count = sum(1 for r in month_records if r.clock_in is not None)
    total_overtime_minutes = sum(max(0, r.work_minutes - 480) for r in month_records)

    # 自己入力の時給に基づく推定給与計算（通常時給＋残業割増1.25倍）
    hourly_rate = current_user.hourly_wage or 0
    regular_minutes = total_work_minutes - total_overtime_minutes
    regular_pay = (regular_minutes / 60.0) * hourly_rate
    overtime_pay = (total_overtime_minutes / 60.0) * hourly_rate * 1.25
    estimated_salary = int(round(regular_pay + overtime_pay)) if hourly_rate > 0 else 0

    # 4. 有休消化数（当月分）
    paid_leaves_taken = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date >= start_of_month,
        models.Shift.date <= end_of_month,
        models.Shift.shift_type == models.ShiftType.OFF,
        models.Shift.note.like("%有休%")
    ).count()

    # 5. 体調サマリー（直近7日）
    recent_health = db.query(models.PersonalSchedule).filter(
        models.PersonalSchedule.user_id == current_user.id,
        models.PersonalSchedule.category == "HEALTH",
        models.PersonalSchedule.date >= today.replace(day=max(1, today.day - 7))
    ).order_by(models.PersonalSchedule.date.desc()).all()

    # 6. 当月の家計簿集計
    budget_records = db.query(models.PersonalSchedule).filter(
        models.PersonalSchedule.user_id == current_user.id,
        models.PersonalSchedule.category == "BUDGET",
        models.PersonalSchedule.date >= start_of_month,
        models.PersonalSchedule.date <= end_of_month
    ).all()

    total_income = sum(b.amount for b in budget_records if b.is_income)
    total_expense = sum(b.amount for b in budget_records if not b.is_income)

    # 7. 未読メッセージ数
    unread_msg_count = db.query(models.Message).filter(
        models.Message.to_user_id == current_user.id,
        models.Message.is_read == False
    ).count()

    today_int = int(today.strftime("%Y%m%d"))
    daily_thought = GENTLE_THOUGHTS[today_int % len(GENTLE_THOUGHTS)]

    return {
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "position_label": current_user.position_label,
            "employment_type": current_user.employment_type.value,
            "evaluation_color": current_user.evaluation_color,
            "theme_color": current_user.theme_color,
            "theme_bg": current_user.theme_bg,
            "hourly_wage": current_user.hourly_wage,
            "paid_leave_remaining": current_user.paid_leave_remaining,
        },
        "gentle_thought": daily_thought,
        "theme_palettes": [
            {"id": "rose", "name": "ローズピンク", "color": "#f43f5e"},
            {"id": "blue", "name": "パウダーブルー", "color": "#0284c7"},
            {"id": "mint", "name": "ミントグリーン", "color": "#059669"},
            {"id": "champagne", "name": "シャンパンアイボリー", "color": "#d97706"},
            {"id": "lavender", "name": "ラベンダー", "color": "#7c3aed"}
        ],
        "today_shift": {
            "shift_type": today_shift.shift_type.value if today_shift else "OFF",
            "shift_label": today_shift.shift_label if today_shift else "休み",
            "time_range": today_shift.time_range if today_shift else "お休み",
        },
        "clock": {
            "status": clock_status,
            "clock_in": clock_in_str,
            "clock_out": clock_out_str,
        },
        "salary_simulator": {
            "hourly_wage": hourly_rate,
            "total_work_minutes": total_work_minutes,
            "total_work_hours": round(total_work_minutes / 60.0, 1),
            "worked_days_count": worked_days_count,
            "overtime_minutes": total_overtime_minutes,
            "overtime_hours": round(total_overtime_minutes / 60.0, 1),
            "estimated_salary": estimated_salary,
            "daily_records": [
                {
                    "date": r.date.isoformat(),
                    "clock_in": r.clock_in.strftime("%H:%M") if r.clock_in else None,
                    "clock_out": r.clock_out.strftime("%H:%M") if r.clock_out else None,
                    "work_minutes": r.work_minutes,
                    "work_hours": round(r.work_minutes / 60.0, 1),
                    "overtime_minutes": max(0, r.work_minutes - 480),
                }
                for r in month_records
            ]
        },
        "paid_leave": {
            "remaining": current_user.paid_leave_remaining,
            "taken_this_month": paid_leaves_taken,
        },
        "health": {
            "recent": [
                {"date": h.date.isoformat(), "status": h.health_status, "note": h.note}
                for h in recent_health
            ]
        },
        "budget": {
            "income": total_income,
            "expense": total_expense,
            "balance": total_income - total_expense,
        },
        "unread_msg_count": unread_msg_count,
    }


@router.get("/gentle-thought")
def get_gentle_thought():
    """恋人に伝えるかのような心温まる英語の感謝メッセージを日替わりで配信"""
    today_int = int(date.today().strftime("%Y%m%d"))
    return {
        "thought": GENTLE_THOUGHTS[today_int % len(GENTLE_THOUGHTS)],
        "count": len(GENTLE_THOUGHTS),
        "all_thoughts": GENTLE_THOUGHTS
    }


# --- 1. 給与シミュレーターAPI（自己入力設定） ---
@router.put("/wage")
def update_my_wage(
    data: WageUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """自分の時間給を自分で入力して保存（自己責任計算用）"""
    current_user.hourly_wage = max(0, data.hourly_wage)
    db.commit()
    return {"success": True, "hourly_wage": current_user.hourly_wage}


# --- 2. 有休管理API（自己入力設定） ---
@router.put("/paid-leave")
def update_my_paid_leave(
    data: PaidLeaveUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """有給残日数を自分で入力して保存（自己管理用）"""
    current_user.paid_leave_remaining = max(0.0, data.paid_leave_remaining)
    db.commit()
    return {"success": True, "paid_leave_remaining": current_user.paid_leave_remaining}


# --- 打刻アクション（自己申告） ---
@router.post("/clock")
def do_clock_action(
    data: ClockActionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()
    now_time = datetime.now().time().replace(microsecond=0)

    record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date == today
    ).first()

    if not record:
        record = models.TimeRecord(
            user_id=current_user.id,
            date=today,
            status=models.ClockStatus.NONE
        )
        db.add(record)

    action = data.action
    if action == "IN":
        record.clock_in = now_time
        record.status = models.ClockStatus.WORKING
    elif action == "BREAK_START":
        record.break_start = now_time
        record.status = models.ClockStatus.BREAK
    elif action == "BREAK_END":
        record.break_end = now_time
        record.status = models.ClockStatus.WORKING
    elif action == "OUT":
        record.clock_out = now_time
        record.status = models.ClockStatus.DONE

    db.commit()
    return {
        "success": True,
        "status": record.status.value,
        "clock_in": record.clock_in.strftime("%H:%M") if record.clock_in else None,
        "clock_out": record.clock_out.strftime("%H:%M") if record.clock_out else None,
    }


# --- 3. 体調管理API ---
@router.post("/health")
def record_health(
    data: HealthRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_date = date.fromisoformat(data.date)
    rec = db.query(models.PersonalSchedule).filter(
        models.PersonalSchedule.user_id == current_user.id,
        models.PersonalSchedule.date == target_date,
        models.PersonalSchedule.category == "HEALTH"
    ).first()

    if not rec:
        rec = models.PersonalSchedule(
            user_id=current_user.id,
            date=target_date,
            category="HEALTH"
        )
        db.add(rec)

    rec.health_status = data.health_status
    rec.note = data.note or ""
    db.commit()
    return {"success": True}


# --- 4. 家計簿API ---
@router.post("/budget")
def add_budget_record(
    data: BudgetRecordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_date = date.fromisoformat(data.date)
    rec = models.PersonalSchedule(
        user_id=current_user.id,
        date=target_date,
        title=data.title,
        amount=data.amount,
        is_income=data.is_income,
        category="BUDGET",
        note=data.note or ""
    )
    db.add(rec)
    db.commit()
    return {"success": True, "id": rec.id}


@router.get("/budget/records")
def get_budget_records(
    year: int,
    month: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _, days_in_month = calendar.monthrange(year, month)
    items = db.query(models.PersonalSchedule).filter(
        models.PersonalSchedule.user_id == current_user.id,
        models.PersonalSchedule.category == "BUDGET",
        models.PersonalSchedule.date >= date(year, month, 1),
        models.PersonalSchedule.date <= date(year, month, days_in_month)
    ).order_by(models.PersonalSchedule.date.desc()).all()

    return [
        {
            "id": it.id,
            "date": it.date.isoformat(),
            "title": it.title,
            "amount": it.amount,
            "is_income": it.is_income,
            "note": it.note,
        }
        for it in items
    ]


# --- 5. 休暇申請（スタッフから管理者へ直送・他スタッフ完全遮断） ---
@router.post("/leave-requests")
def submit_leave_request(
    data: LeaveApplyRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_date = date.fromisoformat(data.date)
    item = models.LeaveRequest(
        user_id=current_user.id,
        date=target_date,
        request_type=data.request_type,
        leave_type=data.leave_type,
        reason=data.reason or "",
        status=models.RequestStatus.PENDING
    )
    db.add(item)
    db.commit()
    return {"success": True, "id": item.id}


@router.get("/leave-requests")
def get_my_leave_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == current_user.id
    ).order_by(models.LeaveRequest.date.desc()).all()

    return [
        {
            "id": it.id,
            "date": it.date.isoformat(),
            "request_type": it.request_type,
            "leave_type": it.leave_type,
            "reason": it.reason,
            "status": it.status.value,
            "admin_note": it.admin_note,
        }
        for it in items
    ]


# --- 6. 個別メッセージ（受信箱） ---
@router.get("/messages")
def get_my_messages(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msgs = db.query(models.Message).filter(
        models.Message.to_user_id == current_user.id
    ).order_by(models.Message.created_at.desc()).all()

    # 既読に更新
    for m in msgs:
        m.is_read = True
    db.commit()

    return [
        {
            "id": m.id,
            "sender_name": m.sender.full_name,
            "content": m.content,
            "created_at": m.created_at.strftime("%Y/%m/%d %H:%M"),
        }
        for m in msgs
    ]


# --- 7. マイルームカスタマイズ（テーマカラー・背景） ---
@router.put("/theme")
def update_my_theme(
    data: ThemeUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.theme_color = data.theme_color
    current_user.theme_bg = data.theme_bg
    db.commit()
    return {"success": True, "theme_color": current_user.theme_color, "theme_bg": current_user.theme_bg}
