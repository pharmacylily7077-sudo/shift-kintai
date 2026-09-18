import calendar
from datetime import datetime, date, time, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract, and_
from database import get_db
import models
import schemas
from auth import get_current_user

router = APIRouter(prefix="/api/me", tags=["staff"])

@router.get("/dashboard", response_model=schemas.StaffDashboardResponse)
def get_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()

    # 1. 今日の打刻レコード取得
    today_record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date == today
    ).first()

    today_status = today_record.status if today_record else "NONE"

    # 2. 今日のシフト取得
    today_shift = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date == today
    ).first()

    today_shift_res = None
    if today_shift:
        today_shift_res = schemas.ShiftResponse(
            id=today_shift.id,
            user_id=today_shift.user_id,
            date=today_shift.date,
            start_time=today_shift.start_time,
            end_time=today_shift.end_time,
            break_minutes=today_shift.break_minutes,
            shift_type=today_shift.shift_type,
            note=today_shift.note,
            user_name=current_user.full_name
        )

    # 3. 当月の確定労働時間・給与計算
    # 当月の初日と最終日
    first_day_of_month = today.replace(day=1)
    _, last_day_num = calendar.monthrange(today.year, today.month)
    last_day_of_month = today.replace(day=last_day_num)

    # 当月の全打刻レコード
    records_this_month = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date >= first_day_of_month,
        models.TimeRecord.date <= last_day_of_month
    ).all()

    confirmed_minutes = sum(r.total_work_minutes for r in records_this_month)
    
    # 有休手当の計算
    daily_scheduled_minutes = current_user.get_daily_scheduled_minutes()
    
    # 当月消化済みの有休（1日〜今日まで）
    confirmed_paid_leave_count = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date >= first_day_of_month,
        models.Shift.date <= today,
        models.Shift.shift_type == "PAID_LEAVE"
    ).count()

    hourly_wage = current_user.hourly_wage
    if current_user.wage_type == "MONTHLY":
        # 月給制の場合は基本給をベース
        confirmed_salary = current_user.monthly_salary
    else:
        paid_leave_allowance = round((daily_scheduled_minutes / 60.0) * hourly_wage * confirmed_paid_leave_count)
        confirmed_salary = round((confirmed_minutes / 60.0) * hourly_wage) + paid_leave_allowance

    # 4. 月末着地見込み計算（今日以降の予定シフト）
    # 今日以降の当月通常シフト
    upcoming_shifts = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date >= today,
        models.Shift.date <= last_day_of_month,
        models.Shift.shift_type == "NORMAL"
    ).all()

    projected_remaining_minutes = 0
    for s in upcoming_shifts:
        # 今日のシフトですでに打刻済み（WORKINGまたはLEFT）の場合は重複計算しない
        if s.date == today and today_record and today_record.status in ["WORKING", "ON_BREAK", "LEFT"]:
            continue
        if s.start_time and s.end_time:
            start_dt = datetime.combine(s.date, s.start_time)
            end_dt = datetime.combine(s.date, s.end_time)
            if end_dt > start_dt:
                diff_min = int((end_dt - start_dt).total_seconds() // 60)
                work_min = max(0, diff_min - (s.break_minutes or 0))
                projected_remaining_minutes += work_min

    # 今日以降の当月有休シフト
    upcoming_paid_leave_count = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date > today,
        models.Shift.date <= last_day_of_month,
        models.Shift.shift_type == "PAID_LEAVE"
    ).count()

    if current_user.wage_type == "MONTHLY":
        projected_remaining_salary = 0
        projected_month_end_salary = current_user.monthly_salary
    else:
        upcoming_paid_leave_allowance = round((daily_scheduled_minutes / 60.0) * hourly_wage * upcoming_paid_leave_count)
        projected_remaining_salary = round((projected_remaining_minutes / 60.0) * hourly_wage) + upcoming_paid_leave_allowance
        projected_month_end_salary = confirmed_salary + projected_remaining_salary

    # 5. 扶養枠シミュレーション (103万・130万)
    # 当月の着地見込み額から年換算ペースを試算（月見込み × 12）
    annual_pace_salary = projected_month_end_salary * 12

    tax_103_limit = 1030000
    tax_103_remaining = max(0, tax_103_limit - annual_pace_salary)
    tax_103_hours = round(tax_103_remaining / (hourly_wage if hourly_wage > 0 else 1000), 1)

    tax_130_limit = 1300000
    tax_130_remaining = max(0, tax_130_limit - annual_pace_salary)
    tax_130_hours = round(tax_130_remaining / (hourly_wage if hourly_wage > 0 else 1000), 1)

    # 6. 有給休暇サマリー
    total_paid_leave = current_user.paid_leave_granted + current_user.paid_leave_carried
    
    # 今年度消化日数（当年1月1日〜現在までの PAID_LEAVE シフト数）
    year_start = date(today.year, 1, 1)
    used_paid_leave_count = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date >= year_start,
        models.Shift.date <= today,
        models.Shift.shift_type == "PAID_LEAVE"
    ).count()

    remaining_paid_leave = max(0.0, total_paid_leave - used_paid_leave_count)
    legal_progress = min(1.0, used_paid_leave_count / 5.0) if total_paid_leave >= 10 else 1.0
    # 年5日取得義務警告（10日以上付与対象者で半年経過して2日未満など、または年後半で5日未満）
    paid_leave_warning = (total_paid_leave >= 10.0 and today.month >= 7 and used_paid_leave_count < 3)

    return schemas.StaffDashboardResponse(
        user=schemas.UserResponse.model_validate(current_user),
        today_status=today_status,
        today_record=schemas.TimeRecordResponse.model_validate(today_record) if today_record else None,
        today_shift=today_shift_res,
        current_month_name=f"{today.year}年{today.month}月",
        confirmed_work_minutes=confirmed_minutes,
        confirmed_salary=confirmed_salary,
        projected_remaining_minutes=projected_remaining_minutes,
        projected_remaining_salary=projected_remaining_salary,
        projected_month_end_salary=projected_month_end_salary,
        annual_pace_salary=annual_pace_salary,
        tax_103_limit=tax_103_limit,
        tax_103_remaining=tax_103_remaining,
        tax_103_hours_remaining=tax_103_hours,
        tax_130_limit=tax_130_limit,
        tax_130_remaining=tax_130_remaining,
        tax_130_hours_remaining=tax_130_hours,
        paid_leave_total=total_paid_leave,
        paid_leave_used=float(used_paid_leave_count),
        paid_leave_remaining=remaining_paid_leave,
        paid_leave_legal_obligation_progress=legal_progress,
        paid_leave_warning=paid_leave_warning
    )

@router.post("/clock", response_model=schemas.TimeRecordResponse)
def clock_action(
    request_data: schemas.ClockRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = datetime.now()
    today = now.date()

    # 今日の打刻レコードを取得、なければ作成
    record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date == today
    ).first()

    action = request_data.action

    if action == "IN":  # 出勤
        if record and record.status != "NONE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="すでに出勤記録が存在します（二重打刻防止）"
            )
        if not record:
            record = models.TimeRecord(
                user_id=current_user.id,
                date=today,
                clock_in=now,
                status="WORKING",
                note=request_data.note
            )
            db.add(record)
        else:
            record.clock_in = now
            record.status = "WORKING"
            if request_data.note:
                record.note = request_data.note

    elif action == "BREAK_START":  # 休憩入
        if not record or record.status != "WORKING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="勤務中ではないため、休憩を開始できません"
            )
        record.break_start = now
        record.status = "ON_BREAK"

    elif action == "BREAK_END":  # 休憩戻
        if not record or record.status != "ON_BREAK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="休憩中ではないため、休憩を終了できません"
            )
        record.break_end = now
        if record.break_start:
            break_mins = int((now - record.break_start).total_seconds() // 60)
            record.total_break_minutes += max(0, break_mins)
        record.break_start = None
        record.break_end = None
        record.status = "WORKING"

    elif action == "OUT":  # 退勤
        if not record or record.status not in ["WORKING", "ON_BREAK"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="勤務中ではないため、退勤できません"
            )
        # 休憩中のまま退勤を押した場合は休憩終了分を加算
        if record.status == "ON_BREAK" and record.break_start:
            break_mins = int((now - record.break_start).total_seconds() // 60)
            record.total_break_minutes += max(0, break_mins)
            record.break_start = None

        record.clock_out = now
        record.status = "LEFT"

        # 実労働時間計算
        if record.clock_in:
            diff_mins = int((record.clock_out - record.clock_in).total_seconds() // 60)
            record.total_work_minutes = max(0, diff_mins - record.total_break_minutes)

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不正な打刻アクションです"
        )

    db.commit()
    db.refresh(record)
    return record

@router.get("/shifts")
def get_my_shifts(
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    first_day = date(target_year, target_month, 1)
    _, last_day_num = calendar.monthrange(target_year, target_month)
    last_day = date(target_year, target_month, last_day_num)

    shifts = db.query(models.Shift).filter(
        models.Shift.user_id == current_user.id,
        models.Shift.date >= first_day,
        models.Shift.date <= last_day
    ).order_by(models.Shift.date.asc()).all()

    records = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date >= first_day,
        models.TimeRecord.date <= last_day
    ).all()

    records_by_date = {r.date.isoformat(): r for r in records}

    shift_requests = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.user_id == current_user.id,
        models.ShiftRequest.date >= first_day,
        models.ShiftRequest.date <= last_day
    ).all()
    requests_by_date = {r.date.isoformat(): r for r in shift_requests}

    # 日付ごとのサマリーリストを構築
    result = []
    shifts_by_date = {s.date.isoformat(): s for s in shifts}

    for day in range(1, last_day_num + 1):
        d = date(target_year, target_month, day)
        d_str = d.isoformat()
        shift = shifts_by_date.get(d_str)
        record = records_by_date.get(d_str)
        s_req = requests_by_date.get(d_str)

        result.append({
            "date": d_str,
            "day": day,
            "weekday": d.strftime("%a"),
            "shift": {
                "id": shift.id,
                "start_time": shift.start_time.strftime("%H:%M") if shift and shift.start_time else None,
                "end_time": shift.end_time.strftime("%H:%M") if shift and shift.end_time else None,
                "break_minutes": shift.break_minutes if shift else None,
                "shift_type": shift.shift_type if shift else None,
                "note": shift.note if shift else None
            } if shift else None,
            "record": {
                "id": record.id,
                "clock_in": record.clock_in.strftime("%H:%M") if record and record.clock_in else None,
                "clock_out": record.clock_out.strftime("%H:%M") if record and record.clock_out else None,
                "total_work_minutes": record.total_work_minutes if record else 0,
                "status": record.status if record else "NONE",
                "is_corrected": record.is_corrected if record else False
            } if record else None,
            "shift_request": {
                "id": s_req.id,
                "request_type": s_req.request_type,
                "status": s_req.status,
                "reason": s_req.reason,
                "admin_comment": s_req.admin_comment
            } if s_req else None
        })

    return result

@router.put("/settings", response_model=schemas.UserResponse)
def update_my_settings(
    settings_data: schemas.UserSettingsUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if settings_data.hourly_wage is not None:
        if settings_data.hourly_wage < 0:
            raise HTTPException(status_code=400, detail="時給は0以上で設定してください")
        current_user.hourly_wage = settings_data.hourly_wage

    if settings_data.paid_leave_granted is not None:
        if settings_data.paid_leave_granted < 0:
            raise HTTPException(status_code=400, detail="有休付与日数は0以上で設定してください")
        current_user.paid_leave_granted = settings_data.paid_leave_granted

    if settings_data.paid_leave_carried is not None:
        if settings_data.paid_leave_carried < 0:
            raise HTTPException(status_code=400, detail="有休繰越日数は0以上で設定してください")
        current_user.paid_leave_carried = settings_data.paid_leave_carried

    if settings_data.paid_leave_base_date is not None:
        current_user.paid_leave_base_date = settings_data.paid_leave_base_date

    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/correction-request", response_model=schemas.CorrectionRequestResponse)
def create_correction_request(
    req: schemas.CorrectionRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 該当日のレコードがあれば紐付け
    record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == current_user.id,
        models.TimeRecord.date == req.target_date
    ).first()

    req_clock_in = None
    if req.requested_clock_in:
        try:
            if " " in req.requested_clock_in:
                req_clock_in = datetime.strptime(req.requested_clock_in, "%Y-%m-%d %H:%M")
            else:
                t = datetime.strptime(req.requested_clock_in, "%H:%M").time()
                req_clock_in = datetime.combine(req.target_date, t)
        except Exception:
            raise HTTPException(status_code=400, detail="出勤希望時刻の形式が不正です (例: 09:00)")

    req_clock_out = None
    if req.requested_clock_out:
        try:
            if " " in req.requested_clock_out:
                req_clock_out = datetime.strptime(req.requested_clock_out, "%Y-%m-%d %H:%M")
            else:
                t = datetime.strptime(req.requested_clock_out, "%H:%M").time()
                req_clock_out = datetime.combine(req.target_date, t)
        except Exception:
            raise HTTPException(status_code=400, detail="退勤希望時刻の形式が不正です (例: 18:00)")

    correction = models.CorrectionRequest(
        user_id=current_user.id,
        time_record_id=record.id if record else None,
        target_date=req.target_date,
        requested_clock_in=req_clock_in,
        requested_clock_out=req_clock_out,
        requested_break_minutes=req.requested_break_minutes,
        reason=req.reason,
        status="PENDING"
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)

    res = schemas.CorrectionRequestResponse.model_validate(correction)
    res.user_name = current_user.full_name
    return res

@router.get("/correction-requests", response_model=List[schemas.CorrectionRequestResponse])
def get_my_correction_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    requests = db.query(models.CorrectionRequest).filter(
        models.CorrectionRequest.user_id == current_user.id
    ).order_by(models.CorrectionRequest.created_at.desc()).all()

    res = []
    for r in requests:
        item = schemas.CorrectionRequestResponse.model_validate(r)
        item.user_name = current_user.full_name
        res.append(item)
    return res

# --- シフト希望（休み希望・有休希望）提出・取得・取消 ---
@router.post("/shift-requests", response_model=schemas.ShiftRequestResponse)
def submit_shift_request(
    req: schemas.ShiftRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if req.request_type not in ["OFF", "PAID_LEAVE"]:
        raise HTTPException(status_code=400, detail="区分は OFF（希望休）または PAID_LEAVE（有休）を指定してください")

    # 同日・同ユーザーの既存申請があれば上書き更新、なければ新規作成
    existing = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.user_id == current_user.id,
        models.ShiftRequest.date == req.date
    ).first()

    if existing:
        existing.request_type = req.request_type
        existing.reason = req.reason
        existing.status = "PENDING"
        existing.admin_comment = None
        db.commit()
        db.refresh(existing)
        res = schemas.ShiftRequestResponse.model_validate(existing)
        res.user_name = current_user.full_name
        return res

    new_req = models.ShiftRequest(
        user_id=current_user.id,
        date=req.date,
        request_type=req.request_type,
        reason=req.reason,
        status="PENDING"
    )
    db.add(new_req)
    db.commit()
    db.refresh(new_req)

    res = schemas.ShiftRequestResponse.model_validate(new_req)
    res.user_name = current_user.full_name
    return res

@router.get("/shift-requests", response_model=List[schemas.ShiftRequestResponse])
def get_my_shift_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    requests = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.user_id == current_user.id
    ).order_by(models.ShiftRequest.date.asc()).all()

    res = []
    for r in requests:
        item = schemas.ShiftRequestResponse.model_validate(r)
        item.user_name = current_user.full_name
        res.append(item)
    return res

@router.delete("/shift-requests/{request_id}")
def cancel_shift_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.id == request_id,
        models.ShiftRequest.user_id == current_user.id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="シフト希望が見つかりません")

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="審査完了済みの希望は取り消せません。管理者に直接ご相談ください")

    db.delete(req)
    db.commit()
    return {"message": "シフト希望を取り消しました"}
