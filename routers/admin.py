import io
import csv
import calendar
from datetime import datetime, date, time
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from auth import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users", response_model=List[schemas.UserResponse])
def get_users(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    users = db.query(models.User).filter(models.User.is_active == True).all()
    return users

@router.put("/users/{user_id}/condition", response_model=schemas.UserResponse)
def update_user_condition(
    user_id: int,
    cond: schemas.UserConditionUpdate,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    if cond.work_days is not None:
        user.work_days = cond.work_days
    if cond.default_start_time is not None:
        if cond.default_start_time:
            try:
                user.default_start_time = datetime.strptime(cond.default_start_time, "%H:%M").time()
            except Exception:
                raise HTTPException(status_code=400, detail="開始時刻の形式が不正です (例: 09:00)")
        else:
            user.default_start_time = None
    if cond.default_end_time is not None:
        if cond.default_end_time:
            try:
                user.default_end_time = datetime.strptime(cond.default_end_time, "%H:%M").time()
            except Exception:
                raise HTTPException(status_code=400, detail="終了時刻の形式が不正です (例: 18:00)")
        else:
            user.default_end_time = None
    if cond.default_break_minutes is not None:
        user.default_break_minutes = cond.default_break_minutes
    if cond.color is not None:
        user.color = cond.color
    if cond.hourly_wage is not None:
        user.hourly_wage = cond.hourly_wage

    db.commit()
    db.refresh(user)
    return user

@router.get("/attendance/summary")
def get_attendance_summary(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.now()

    # 全スタッフ取得（admin自身も除外または含める）
    staff_users = db.query(models.User).filter(
        models.User.role == "staff",
        models.User.is_active == True
    ).all()

    # 今日のシフト
    shifts = db.query(models.Shift).filter(models.Shift.date == today).all()
    shifts_by_user = {s.user_id: s for s in shifts}

    # 今日の打刻
    records = db.query(models.TimeRecord).filter(models.TimeRecord.date == today).all()
    records_by_user = {r.user_id: r for r in records}

    summary = []
    for user in staff_users:
        shift = shifts_by_user.get(user.id)
        record = records_by_user.get(user.id)

        status_text = "未出勤"
        is_alert = False
        alert_message = ""

        if record:
            if record.status == "WORKING":
                status_text = "勤務中"
            elif record.status == "ON_BREAK":
                status_text = "休憩中"
            elif record.status == "LEFT":
                status_text = "退勤済"
        
        # シフト予定があるのに打刻がない場合のアラート
        if shift and shift.shift_type == "NORMAL":
            if shift.start_time:
                scheduled_start_dt = datetime.combine(today, shift.start_time)
                # 始業予定を15分以上過ぎて未出勤
                if not record and now > scheduled_start_dt:
                    is_alert = True
                    alert_message = "始業予定を過ぎていますが未打刻です"
        elif shift and shift.shift_type == "PAID_LEAVE":
            status_text = "有給休暇"
        elif shift and shift.shift_type == "HOLIDAY":
            status_text = "公休"

        summary.append({
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "wage_type": user.wage_type,
            "hourly_wage": user.hourly_wage,
            "shift": {
                "id": shift.id,
                "start_time": shift.start_time.strftime("%H:%M") if shift and shift.start_time else None,
                "end_time": shift.end_time.strftime("%H:%M") if shift and shift.end_time else None,
                "shift_type": shift.shift_type if shift else "OFF"
            } if shift else None,
            "record": {
                "id": record.id,
                "clock_in": record.clock_in.strftime("%H:%M") if record and record.clock_in else None,
                "clock_out": record.clock_out.strftime("%H:%M") if record and record.clock_out else None,
                "total_work_minutes": record.total_work_minutes if record else 0,
                "status": record.status if record else "NONE"
            } if record else None,
            "status_text": status_text,
            "is_alert": is_alert,
            "alert_message": alert_message
        })

    return summary

@router.get("/shifts")
def get_all_shifts(
    year: int = Query(default=None),
    month: int = Query(default=None),
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    first_day = date(target_year, target_month, 1)
    _, last_day_num = calendar.monthrange(target_year, target_month)
    last_day = date(target_year, target_month, last_day_num)

    shifts = db.query(models.Shift).filter(
        models.Shift.date >= first_day,
        models.Shift.date <= last_day
    ).all()

    all_users = db.query(models.User).all()
    user_names = {u.id: u.full_name for u in all_users}
    user_colors = {u.id: u.color or "#059669" for u in all_users}

    result = []
    for s in shifts:
        result.append({
            "id": s.id,
            "user_id": s.user_id,
            "user_name": user_names.get(s.user_id, "不明"),
            "user_color": user_colors.get(s.user_id, "#059669"),
            "date": s.date.isoformat(),
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
            "break_minutes": s.break_minutes,
            "shift_type": s.shift_type,
            "note": s.note
        })
    return result

@router.post("/shifts/auto-generate")
def auto_generate_monthly_shifts(
    req: schemas.ShiftAutoGenerateRequest,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    year = req.year
    month = req.month
    first_day = date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_num)

    # 有効な全スタッフ取得
    staff_users = db.query(models.User).filter(
        models.User.role == "staff",
        models.User.is_active == True
    ).all()

    # 該当月の承認済みシフト希望取得
    approved_requests = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.date >= first_day,
        models.ShiftRequest.date <= last_day,
        models.ShiftRequest.status == "APPROVED"
    ).all()
    requests_map = {(r.user_id, r.date): r for r in approved_requests}

    # 該当月の既存シフト取得
    existing_shifts = db.query(models.Shift).filter(
        models.Shift.date >= first_day,
        models.Shift.date <= last_day
    ).all()
    existing_map = {(s.user_id, s.date): s for s in existing_shifts}

    generated_count = 0
    skipped_count = 0
    updated_count = 0

    for user in staff_users:
        # work_days: "0,1,2,4,5" (0=月..6=日)
        work_day_list = []
        if user.work_days:
            for w in user.work_days.split(","):
                w_str = w.strip()
                if w_str.isdigit():
                    work_day_list.append(int(w_str))

        for d_num in range(1, last_day_num + 1):
            cur_date = date(year, month, d_num)
            weekday = cur_date.weekday()

            cur_shift = existing_map.get((user.id, cur_date))
            if cur_shift and not req.overwrite:
                continue

            s_req = requests_map.get((user.id, cur_date))

            if s_req:
                if s_req.request_type == "OFF":
                    # 希望休（OFF）: 自動スキップ
                    if cur_shift and req.overwrite:
                        db.delete(cur_shift)
                        updated_count += 1
                    skipped_count += 1
                    continue
                elif s_req.request_type == "PAID_LEAVE":
                    # 有休希望: PAID_LEAVE シフト生成
                    if cur_shift:
                        cur_shift.shift_type = "PAID_LEAVE"
                        cur_shift.start_time = None
                        cur_shift.end_time = None
                        cur_shift.break_minutes = 0
                        cur_shift.note = s_req.reason or "有給休暇（希望休承認）"
                        updated_count += 1
                    else:
                        new_shift = models.Shift(
                            user_id=user.id,
                            date=cur_date,
                            start_time=None,
                            end_time=None,
                            break_minutes=0,
                            shift_type="PAID_LEAVE",
                            note=s_req.reason or "有給休暇（希望休承認）"
                        )
                        db.add(new_shift)
                        generated_count += 1
                    continue

            # 希望休がない場合、基本勤務曜日かをチェック
            if weekday in work_day_list:
                s_time = user.default_start_time or time(9, 0)
                e_time = user.default_end_time or time(18, 0)
                b_min = user.default_break_minutes if user.default_break_minutes is not None else 60

                if cur_shift:
                    cur_shift.shift_type = "NORMAL"
                    cur_shift.start_time = s_time
                    cur_shift.end_time = e_time
                    cur_shift.break_minutes = b_min
                    cur_shift.note = "一括自動生成シフト"
                    updated_count += 1
                else:
                    new_shift = models.Shift(
                        user_id=user.id,
                        date=cur_date,
                        start_time=s_time,
                        end_time=e_time,
                        break_minutes=b_min,
                        shift_type="NORMAL",
                        note="一括自動生成シフト"
                    )
                    db.add(new_shift)
                    generated_count += 1
            else:
                # 基本勤務曜日でない場合、上書き指定なら既存の通常シフトを削除してクリーンアップ
                if cur_shift and req.overwrite and cur_shift.shift_type == "NORMAL":
                    db.delete(cur_shift)
                    updated_count += 1

    db.commit()
    return {
        "message": f"{year}年{month}月のシフトを一括生成しました",
        "generated": generated_count,
        "updated": updated_count,
        "skipped_requests": skipped_count
    }

@router.post("/shifts")
def create_or_update_shift(
    req: schemas.ShiftCreate,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    start_t = None
    if req.start_time:
        try:
            start_t = datetime.strptime(req.start_time, "%H:%M").time()
        except Exception:
            raise HTTPException(status_code=400, detail="開始時刻の形式が不正です (例: 09:00)")

    end_t = None
    if req.end_time:
        try:
            end_t = datetime.strptime(req.end_time, "%H:%M").time()
        except Exception:
            raise HTTPException(status_code=400, detail="終了時刻の形式が不正です (例: 18:00)")

    # 同一ユーザー・同一日のシフトがあるか確認
    shift = db.query(models.Shift).filter(
        models.Shift.user_id == req.user_id,
        models.Shift.date == req.date
    ).first()

    if shift:
        shift.start_time = start_t
        shift.end_time = end_t
        shift.break_minutes = req.break_minutes
        shift.shift_type = req.shift_type
        shift.note = req.note
    else:
        shift = models.Shift(
            user_id=req.user_id,
            date=req.date,
            start_time=start_t,
            end_time=end_t,
            break_minutes=req.break_minutes,
            shift_type=req.shift_type,
            note=req.note
        )
        db.add(shift)

    db.commit()
    db.refresh(shift)
    return {"message": "シフトを保存しました", "shift_id": shift.id}

@router.delete("/shifts/{shift_id}")
def delete_shift(
    shift_id: int,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")
    db.delete(shift)
    db.commit()
    return {"message": "シフトを削除しました"}

@router.get("/correction-requests", response_model=List[schemas.CorrectionRequestResponse])
def get_all_correction_requests(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    requests = db.query(models.CorrectionRequest).order_by(
        models.CorrectionRequest.created_at.desc()
    ).all()

    users = {u.id: u.full_name for u in db.query(models.User).all()}

    result = []
    for r in requests:
        item = schemas.CorrectionRequestResponse.model_validate(r)
        item.user_name = users.get(r.user_id, "不明")
        result.append(item)
    return result

@router.post("/correction-requests/{request_id}/review")
def review_correction_request(
    request_id: int,
    review_data: schemas.CorrectionRequestReview,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    req = db.query(models.CorrectionRequest).filter(
        models.CorrectionRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="修正申請が見つかりません")

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="この申請は既に処理されています")

    req.status = review_data.status
    req.admin_comment = review_data.admin_comment

    # 承認の場合、該当日の実打刻レコードを更新または新規作成
    if review_data.status == "APPROVED":
        record = None
        if req.time_record_id:
            record = db.query(models.TimeRecord).filter(models.TimeRecord.id == req.time_record_id).first()
        if not record:
            record = db.query(models.TimeRecord).filter(
                models.TimeRecord.user_id == req.user_id,
                models.TimeRecord.date == req.target_date
            ).first()

        if not record:
            record = models.TimeRecord(
                user_id=req.user_id,
                date=req.target_date,
                status="LEFT",
                is_corrected=True
            )
            db.add(record)

        if req.requested_clock_in:
            record.clock_in = req.requested_clock_in
        if req.requested_clock_out:
            record.clock_out = req.requested_clock_out
        record.total_break_minutes = req.requested_break_minutes
        record.is_corrected = True
        record.status = "LEFT"

        # 労働時間の再計算
        if record.clock_in and record.clock_out:
            diff_mins = int((record.clock_out - record.clock_in).total_seconds() // 60)
            record.total_work_minutes = max(0, diff_mins - record.total_break_minutes)

    db.commit()
    return {"message": f"申請を {review_data.status} として処理しました"}

@router.get("/shift-requests", response_model=List[schemas.ShiftRequestResponse])
def get_all_shift_requests(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    requests = db.query(models.ShiftRequest).order_by(
        models.ShiftRequest.date.asc(),
        models.ShiftRequest.created_at.desc()
    ).all()

    users = {u.id: u.full_name for u in db.query(models.User).all()}

    result = []
    for r in requests:
        item = schemas.ShiftRequestResponse.model_validate(r)
        item.user_name = users.get(r.user_id, "不明")
        result.append(item)
    return result

@router.post("/shift-requests/{request_id}/review")
def review_shift_request(
    request_id: int,
    review_data: schemas.ShiftRequestReview,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    req = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="シフト希望が見つかりません")

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="この申請は既に処理されています")

    req.status = review_data.status
    req.admin_comment = review_data.admin_comment

    # 承認された有休希望の場合、該当日に有休シフトを自動作成/更新
    if review_data.status == "APPROVED" and req.request_type == "PAID_LEAVE":
        existing_shift = db.query(models.Shift).filter(
            models.Shift.user_id == req.user_id,
            models.Shift.date == req.date
        ).first()

        if existing_shift:
            existing_shift.shift_type = "PAID_LEAVE"
            existing_shift.start_time = None
            existing_shift.end_time = None
            existing_shift.break_minutes = 0
            existing_shift.note = req.reason or "有給休暇"
        else:
            new_shift = models.Shift(
                user_id=req.user_id,
                date=req.date,
                start_time=None,
                end_time=None,
                break_minutes=0,
                shift_type="PAID_LEAVE",
                note=req.reason or "有給休暇"
            )
            db.add(new_shift)

    # 承認された希望休（OFF）の場合、もし該当日にシフトが存在していたら削除
    elif review_data.status == "APPROVED" and req.request_type == "OFF":
        existing_shift = db.query(models.Shift).filter(
            models.Shift.user_id == req.user_id,
            models.Shift.date == req.date
        ).first()
        if existing_shift:
            db.delete(existing_shift)

    db.commit()
    return {"message": f"シフト希望を {review_data.status} として処理しました"}

@router.get("/export-csv")
def export_monthly_attendance_csv(
    year: int = Query(default=None),
    month: int = Query(default=None),
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    first_day = date(target_year, target_month, 1)
    _, last_day_num = calendar.monthrange(target_year, target_month)
    last_day = date(target_year, target_month, last_day_num)

    users = db.query(models.User).filter(
        models.User.role == "staff",
        models.User.is_active == True
    ).all()

    output = io.StringIO()
    # Excelで文字化けしない UTF-8 BOM を追加
    output.write('\ufeff')
    writer = csv.writer(output)

    # ヘッダー
    writer.writerow([
        "社員/スタッフID",
        "氏名",
        "給与形態",
        "基本時給/月給",
        "対象年月",
        "出勤日数",
        "有休消化日数",
        "総実労働時間(分)",
        "総実労働時間(時間)",
        "総休憩時間(分)",
        "概算支給額(円)"
    ])

    for user in users:
        records = db.query(models.TimeRecord).filter(
            models.TimeRecord.user_id == user.id,
            models.TimeRecord.date >= first_day,
            models.TimeRecord.date <= last_day
        ).all()

        work_days = len([r for r in records if r.total_work_minutes > 0 or r.clock_in])
        total_work_mins = sum(r.total_work_minutes for r in records)
        total_break_mins = sum(r.total_break_minutes for r in records)

        # 有休消化日数
        paid_leave_shifts = db.query(models.Shift).filter(
            models.Shift.user_id == user.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "PAID_LEAVE"
        ).count()

        hours_str = f"{total_work_mins / 60.0:.2f}"
        
        # 概算給与
        if user.wage_type == "MONTHLY":
            salary = user.monthly_salary
            wage_label = f"月給 {user.monthly_salary:,}円"
        else:
            salary = round((total_work_mins / 60.0) * user.hourly_wage)
            wage_label = f"時給 {user.hourly_wage:,}円"

        writer.writerow([
            user.username,
            user.full_name,
            user.wage_type,
            wage_label,
            f"{target_year}年{target_month}月",
            work_days,
            paid_leave_shifts,
            total_work_mins,
            hours_str,
            total_break_mins,
            salary
        ])

    csv_data = output.getvalue()
    filename = f"kintai_{target_year}_{target_month:02d}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
