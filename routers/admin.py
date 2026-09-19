import io
import csv
import json
import zipfile
import calendar
from datetime import datetime, date, time
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from auth import get_current_admin, hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users", response_model=List[schemas.UserResponse])
def get_users(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    users = db.query(models.User).filter(models.User.is_active == True).all()
    return users

@router.post("/users", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_staff_user(
    user_in: schemas.UserAdminCreate,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(models.User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="このログインIDは既に使用されています")

    start_t = None
    if user_in.default_start_time:
        try:
            start_t = datetime.strptime(user_in.default_start_time, "%H:%M").time()
        except Exception:
            start_t = time(9, 0)

    end_t = None
    if user_in.default_end_time:
        try:
            end_t = datetime.strptime(user_in.default_end_time, "%H:%M").time()
        except Exception:
            end_t = time(18, 0)

    new_user = models.User(
        username=user_in.username,
        password_hash=hash_password(user_in.password),
        full_name=user_in.full_name,
        role="staff",
        wage_type=user_in.wage_type,
        hourly_wage=user_in.hourly_wage,
        monthly_salary=0,
        paid_leave_granted=10.0,
        paid_leave_carried=0.0,
        paid_leave_base_date=date.today(),
        work_days=user_in.work_days,
        weekly_schedule=user_in.weekly_schedule,
        default_start_time=start_t,
        default_end_time=end_t,
        default_break_minutes=user_in.default_break_minutes,
        color=user_in.color or "#059669",
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.delete("/users/{user_id}")
def delete_staff_user(
    user_id: int,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="管理者自身を削除することはできません")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    user_name = user.full_name

    # 1. 該当スタッフのシフト・申請データを完全クリーンアップ（カレンダーや集計から即時抹消）
    db.query(models.Shift).filter(models.Shift.user_id == user_id).delete()
    db.query(models.ShiftRequest).filter(models.ShiftRequest.user_id == user_id).delete()
    db.query(models.CorrectionRequest).filter(models.CorrectionRequest.user_id == user_id).delete()

    # 2. 過去の打刻実績の有無を判定
    has_time_records = db.query(models.TimeRecord).filter(models.TimeRecord.user_id == user_id).count() > 0
    if not has_time_records:
        # 実績が一切ない（テスト登録や追加ミス）場合は完全にDBから削除
        db.delete(user)
    else:
        # 法定保管が必要な実働記録がある場合は無効化＆ログインID競合回避
        user.is_active = False
        if not user.username.startswith("deleted_"):
            user.username = f"deleted_{user.id}_{user.username}"

    db.commit()
    return {"message": f"スタッフ「{user_name}」およびシフトを完全に削除しました"}

@router.post("/reset-all")
def reset_all_staff_and_shifts(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    管理者（三宅様）以外の全スタッフ、全シフト、全打刻、全申請を一括削除（オールクリア）する。
    まっさらな状態から運用を開始するための機能。
    """
    # 1. 管理者以外の全スタッフIDを取得
    staff_users = db.query(models.User).filter(models.User.id != admin.id).all()
    deleted_count = len(staff_users)

    # 2. 全シフト、全打刻、全申請を削除
    db.query(models.Shift).delete()
    db.query(models.TimeRecord).delete()
    db.query(models.ShiftRequest).delete()
    db.query(models.CorrectionRequest).delete()

    # 3. 管理者以外のスタッフアカウントを物理削除
    for u in staff_users:
        db.delete(u)

    db.commit()
    return {
        "message": f"全スタッフ({deleted_count}名)・シフト・勤怠データを一括初期化（オールリセット）しました。管理者（三宅様）のみが保持されています。"
    }

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

    if cond.full_name is not None and cond.full_name.strip():
        user.full_name = cond.full_name.strip()
    if cond.password is not None and cond.password.strip():
        if len(cond.password.strip()) < 4:
            raise HTTPException(status_code=400, detail="パスワードは4文字以上で入力してください")
        user.password_hash = hash_password(cond.password.strip())
    if cond.work_days is not None:
        user.work_days = cond.work_days
    if cond.weekly_schedule is not None:
        user.weekly_schedule = cond.weekly_schedule
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
    if cond.wage_type is not None:
        user.wage_type = cond.wage_type
    if cond.hourly_wage is not None:
        user.hourly_wage = cond.hourly_wage
    if cond.monthly_salary is not None:
        user.monthly_salary = cond.monthly_salary

    db.commit()
    db.refresh(user)
    return user

@router.put("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    req: schemas.UserPasswordReset,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    pwd = (req.password or req.new_password or "").strip()
    if not pwd or len(pwd) < 4:
        raise HTTPException(status_code=400, detail="パスワードは4文字以上で入力してください")
    user.password_hash = hash_password(pwd)
    db.commit()
    return {"message": f"「{user.full_name}」様のパスワードを更新しました"}

@router.get("/attendance/summary")
def get_attendance_summary(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.now()

    # 全スタッフ取得（薬局長自身も含めてリアルタイムモニタリング）
    staff_users = db.query(models.User).filter(
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()

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

    shifts = db.query(models.Shift).join(models.User).filter(
        models.User.is_active == True,
        models.Shift.date >= first_day,
        models.Shift.date <= last_day
    ).all()

    active_users = db.query(models.User).filter(models.User.is_active == True).all()
    user_names = {u.id: u.full_name for u in active_users}
    user_colors = {u.id: u.color or "#059669" for u in active_users}

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

def calculate_month_staff_balance(db: Session, target_year: int, target_month: int):
    first_day = date(target_year, target_month, 1)
    _, last_day_num = calendar.monthrange(target_year, target_month)
    last_day = date(target_year, target_month, last_day_num)

    shifts = db.query(models.Shift).filter(
        models.Shift.date >= first_day,
        models.Shift.date <= last_day,
        models.Shift.shift_type == "NORMAL"
    ).all()

    users = db.query(models.User).filter(models.User.is_active == True).all()
    user_dict = {u.id: u for u in users}

    # 日付ごと集計
    day_shifts = {}
    for d_num in range(1, last_day_num + 1):
        cur_d = date(target_year, target_month, d_num)
        day_shifts[cur_d] = []

    for s in shifts:
        if s.date in day_shifts:
            day_shifts[s.date].append(s)

    days_res = []
    warning_days_count = 0

    for d_num in range(1, last_day_num + 1):
        cur_d = date(target_year, target_month, d_num)
        weekday = cur_d.weekday()  # 0=月..6=日
        s_list = day_shifts[cur_d]

        total_staff = len(s_list)
        pharmacist_count = 0
        clerk_count = 0

        for s in s_list:
            u = user_dict.get(s.user_id)
            if u:
                name_or_role = (u.full_name or "") + (u.role or "")
                # 管理者または薬剤師の表記があるか
                if u.role == "admin" or "薬剤師" in name_or_role or "薬局長" in name_or_role:
                    pharmacist_count += 1
                else:
                    clerk_count += 1

        warning_messages = []
        warning_level = "ok"

        # 判定ルール (月〜土の営業日基準)
        # 日曜日(6)は定休日として通常カウントしない（シフトが0でも警告なし、ある場合は通常表示）
        is_sunday = (weekday == 6)
        if not is_sunday:
            if total_staff == 0:
                warning_level = "danger"
                warning_messages.append("出勤スタッフが0名です（開局不可）")
            elif pharmacist_count == 0:
                warning_level = "danger"
                warning_messages.append("薬剤師が不在です（調剤業務不可）")
            elif total_staff == 1:
                # 1名のみの場合
                warning_level = "warning"
                warning_messages.append("ワンオペ出勤です（休憩・混雑時の応援に注意）")

        has_warning = len(warning_messages) > 0
        if has_warning:
            warning_days_count += 1

        days_res.append(schemas.ShiftDayBalance(
            date=cur_d,
            weekday=weekday,
            total_staff=total_staff,
            pharmacist_count=pharmacist_count,
            clerk_count=clerk_count,
            has_warning=has_warning,
            warning_level=warning_level,
            warning_messages=warning_messages
        ))

    return schemas.ShiftBalanceResponse(
        year=target_year,
        month=target_month,
        days=days_res,
        warning_days_count=warning_days_count
    )

@router.get("/shifts/balance", response_model=schemas.ShiftBalanceResponse)
def get_shifts_balance(
    year: int = Query(default=None),
    month: int = Query(default=None),
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month
    return calculate_month_staff_balance(db, target_year, target_month)

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

    # 有効な全スタッフ（および勤務設定のある管理者）を取得
    staff_users = db.query(models.User).filter(
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

        # 曜日別スケジュールの解析
        schedule_map = {}
        if user.weekly_schedule:
            try:
                schedule_map = json.loads(user.weekly_schedule)
            except Exception:
                schedule_map = {}

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

            # 希望休がない場合、出勤日判定と曜日別時間の取得
            is_working_day = False
            s_time = user.default_start_time or time(9, 0)
            e_time = user.default_end_time or time(18, 0)
            b_min = user.default_break_minutes if user.default_break_minutes is not None else 60

            day_setting = schedule_map.get(str(weekday))
            if day_setting is not None:
                is_working_day = bool(day_setting.get("work", False) or day_setting.get("enabled", False))
                if is_working_day:
                    if day_setting.get("start"):
                        try:
                            s_time = datetime.strptime(day_setting["start"], "%H:%M").time()
                        except Exception:
                            s_time = user.default_start_time or time(9, 0)
                    if day_setting.get("end"):
                        try:
                            e_time = datetime.strptime(day_setting["end"], "%H:%M").time()
                        except Exception:
                            e_time = user.default_end_time or time(18, 0)
                    if day_setting.get("break") is not None:
                        try:
                            b_min = int(day_setting["break"])
                        except Exception:
                            b_min = 60
            else:
                is_working_day = (weekday in work_day_list)

            if is_working_day:
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
                # 勤務日でない場合、上書き指定なら既存通常シフトを削除
                if cur_shift and req.overwrite and cur_shift.shift_type == "NORMAL":
                    db.delete(cur_shift)
                    updated_count += 1

    db.commit()
    balance = calculate_month_staff_balance(db, year, month)
    return {
        "message": f"{year}年{month}月のシフトを一括生成しました",
        "generated": generated_count,
        "updated": updated_count,
        "skipped_requests": skipped_count,
        "warning_days_count": balance.warning_days_count,
        "balance_warnings": [
            {"date": d.date.isoformat(), "level": d.warning_level, "messages": d.warning_messages}
            for d in balance.days if d.has_warning
        ]
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
    db.commit()
    return {
        "message": f"シフト希望を {review_data.status} として処理しました",
        "status": review_data.status
    }

# --- 月次給与・勤怠集計 ---
@router.get("/payroll/monthly", response_model=schemas.MonthlyPayrollResponse)
def get_monthly_payroll(
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
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()

    items = []
    total_payout = 0
    total_minutes_all = 0

    for user in users:
        # 当月打刻レコード
        records = db.query(models.TimeRecord).filter(
            models.TimeRecord.user_id == user.id,
            models.TimeRecord.date >= first_day,
            models.TimeRecord.date <= last_day
        ).all()

        work_days = len([r for r in records if r.total_work_minutes > 0 or r.clock_in])
        total_work_mins = sum(r.total_work_minutes for r in records)
        total_break_mins = sum(r.total_break_minutes for r in records)
        total_minutes_all += total_work_mins

        # 予定シフト日数 (NORMAL)
        scheduled_shifts_count = db.query(models.Shift).filter(
            models.Shift.user_id == user.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "NORMAL"
        ).count()

        # 有休消化日数
        paid_leave_shifts = db.query(models.Shift).filter(
            models.Shift.user_id == user.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "PAID_LEAVE"
        ).count()

        daily_mins = user.get_daily_scheduled_minutes()

        if user.wage_type == "MONTHLY":
            work_sal = user.monthly_salary
            pl_allowance = 0
            est_total = user.monthly_salary
        else:
            work_sal = round((total_work_mins / 60.0) * user.hourly_wage)
            pl_allowance = round((daily_mins / 60.0) * user.hourly_wage * paid_leave_shifts)
            est_total = work_sal + pl_allowance

        total_payout += est_total

        h = total_work_mins // 60
        m = total_work_mins % 60
        h_str = f"{h}時間{m:02d}分"

        items.append(schemas.MonthlyPayrollItem(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            wage_type=user.wage_type,
            hourly_wage=user.hourly_wage,
            monthly_salary=user.monthly_salary,
            work_days_count=work_days,
            scheduled_days_count=scheduled_shifts_count,
            total_work_minutes=total_work_mins,
            total_work_hours_str=h_str,
            total_break_minutes=total_break_mins,
            paid_leave_days_count=float(paid_leave_shifts),
            paid_leave_allowance=pl_allowance,
            work_salary=work_sal,
            total_estimated_salary=est_total
        ))

    return schemas.MonthlyPayrollResponse(
        year=target_year,
        month=target_month,
        items=items,
        total_payout=total_payout,
        total_work_hours=round(total_minutes_all / 60.0, 2)
    )

# --- 管理者によるスタッフ勤怠直接登録・修正 ---
@router.post("/time-records", response_model=schemas.TimeRecordResponse)
@router.post("/time-records/direct", response_model=schemas.TimeRecordResponse)
def update_or_create_time_record(
    req: schemas.AdminTimeRecordUpdate,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    target_user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="対象ユーザーが見つかりません")

    record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == req.user_id,
        models.TimeRecord.date == req.date
    ).first()

    cin_dt = None
    if req.clock_in:
        try:
            if " " in req.clock_in:
                cin_dt = datetime.strptime(req.clock_in, "%Y-%m-%d %H:%M")
            else:
                cin_time = datetime.strptime(req.clock_in, "%H:%M").time()
                cin_dt = datetime.combine(req.date, cin_time)
        except Exception:
            raise HTTPException(status_code=400, detail="出勤時刻の形式が不正です (例: 09:00)")

    cout_dt = None
    if req.clock_out:
        try:
            if " " in req.clock_out:
                cout_dt = datetime.strptime(req.clock_out, "%Y-%m-%d %H:%M")
            else:
                cout_time = datetime.strptime(req.clock_out, "%H:%M").time()
                cout_dt = datetime.combine(req.date, cout_time)
        except Exception:
            raise HTTPException(status_code=400, detail="退勤時刻の形式が不正です (例: 18:00)")

    break_mins = max(0, req.total_break_minutes)

    if not record:
        record = models.TimeRecord(
            user_id=req.user_id,
            date=req.date,
            clock_in=cin_dt,
            clock_out=cout_dt,
            total_break_minutes=break_mins,
            status="LEFT" if cout_dt else ("WORKING" if cin_dt else "NONE"),
            is_corrected=True,
            note=req.note or "管理者直接入力"
        )
        db.add(record)
    else:
        record.clock_in = cin_dt
        record.clock_out = cout_dt
        record.total_break_minutes = break_mins
        record.status = "LEFT" if cout_dt else ("WORKING" if cin_dt else "NONE")
        record.is_corrected = True
        if req.note:
            record.note = req.note

    # 実労働時間計算
    if record.clock_in and record.clock_out:
        diff_mins = int((record.clock_out - record.clock_in).total_seconds() // 60)
        record.total_work_minutes = max(0, diff_mins - record.total_break_minutes)
    else:
        record.total_work_minutes = 0

    db.commit()
    db.refresh(record)
    return record

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
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()

    output = io.StringIO()
    # Excelで文字化けしない UTF-8 BOM を追加
    output.write('\ufeff')
    writer = csv.writer(output)

    # ヘッダー
    writer.writerow([
        "社員/スタッフID",
        "氏名",
        "役職",
        "給与形態",
        "基本時給/月給",
        "対象年月",
        "実働日数",
        "予定シフト日数",
        "有休消化日数",
        "総実労働時間(分)",
        "総実労働時間(時間)",
        "総休憩時間(分)",
        "実労働給与(円)",
        "有休手当(円)",
        "概算総支給額(円)"
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

        # 予定シフト日数
        scheduled_shifts_count = db.query(models.Shift).filter(
            models.Shift.user_id == user.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "NORMAL"
        ).count()

        # 有休消化日数
        paid_leave_shifts = db.query(models.Shift).filter(
            models.Shift.user_id == user.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "PAID_LEAVE"
        ).count()

        daily_mins = user.get_daily_scheduled_minutes()

        if user.wage_type == "MONTHLY":
            work_sal = user.monthly_salary
            pl_allowance = 0
            est_total = user.monthly_salary
            wage_label = f"月給 {user.monthly_salary:,}円"
        else:
            work_sal = round((total_work_mins / 60.0) * user.hourly_wage)
            pl_allowance = round((daily_mins / 60.0) * user.hourly_wage * paid_leave_shifts)
            est_total = work_sal + pl_allowance
            wage_label = f"時給 {user.hourly_wage:,}円"

        hours_str = f"{total_work_mins / 60.0:.2f}"

        writer.writerow([
            user.username,
            user.full_name,
            "管理者" if user.role == "admin" else "スタッフ",
            user.wage_type,
            wage_label,
            f"{target_year}年{target_month}月",
            work_days,
            scheduled_shifts_count,
            paid_leave_shifts,
            total_work_mins,
            hours_str,
            total_break_mins,
            work_sal,
            pl_allowance,
            est_total
        ])

    csv_data = output.getvalue()
    filename = f"kintai_payroll_{target_year}_{target_month:02d}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

# --- フェーズ4: LINE・連絡用テキスト生成 ---
@router.get("/shifts/share-text", response_model=schemas.ShiftShareTextResponse)
def get_shift_share_text(
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
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()

    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]

    staff_texts = []
    full_text_lines = [
        f"【ひまわり調剤薬局 {target_year}年{target_month}月度 確定勤務シフト】\n"
    ]

    for u in users:
        shifts = db.query(models.Shift).filter(
            models.Shift.user_id == u.id,
            models.Shift.date >= first_day,
            models.Shift.date <= last_day,
            models.Shift.shift_type == "NORMAL"
        ).order_by(models.Shift.date.asc()).all()

        days_count = len(shifts)
        role_title = "（管理薬剤師）" if (u.role == "admin" and "管理薬剤師" not in (u.full_name or "")) else ""
        
        user_header = f"■ {u.full_name}{role_title} 様（計 {days_count}日）"
        user_shift_lines = []
        for s in shifts:
            weekday_str = weekdays_ja[s.date.weekday()]
            time_str = ""
            if s.start_time and s.end_time:
                time_str = f" {s.start_time.strftime('%H:%M')}〜{s.end_time.strftime('%H:%M')}"
            note_str = f" ({s.note})" if s.note else ""
            user_shift_lines.append(f"・{s.date.month}/{s.date.day}({weekday_str}){time_str}{note_str}")

        single_staff_text = (
            f"【ひまわり調剤薬局 {target_year}年{target_month}月度 シフト案内】\n"
            f"{u.full_name} 様\n\n"
            f"■ 今月の出勤予定（計 {days_count}日）\n"
            + ("\n".join(user_shift_lines) if user_shift_lines else "・今月の出勤予定はありません")
            + "\n\n※ご確認のうえ、変更希望等がある場合はお早めにご連絡ください。"
        )

        staff_texts.append(schemas.ShiftShareStaffText(
            user_id=u.id,
            user_name=u.full_name,
            days_count=days_count,
            text=single_staff_text
        ))

        full_text_lines.append(user_header)
        if user_shift_lines:
            full_text_lines.extend(user_shift_lines)
        else:
            full_text_lines.append("・出勤予定なし")
        full_text_lines.append("")

    full_text_lines.append("※シフト変更・有休希望のご相談はお早めにお知らせください。")
    full_text = "\n".join(full_text_lines)

    return schemas.ShiftShareTextResponse(
        year=target_year,
        month=target_month,
        full_text=full_text,
        by_staff=staff_texts
    )

# --- フェーズ4: 法定有休 年5日取得義務コンプライアンス判定 ---
@router.get("/compliance/paid-leave", response_model=schemas.PaidLeaveComplianceResponse)
def get_paid_leave_compliance(
    year: int = Query(default=None),
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    target_year = year or today.year
    year_start = date(target_year, 1, 1)
    year_end = date(target_year, 12, 31)

    users = db.query(models.User).filter(
        models.User.is_active == True
    ).order_by(models.User.role.asc(), models.User.id.asc()).all()

    staff_compliance = []
    achieved_count = 0
    in_progress_count = 0
    action_required_count = 0
    target_staff_count = 0

    for u in users:
        total_granted = (u.paid_leave_granted or 0.0) + (u.paid_leave_carried or 0.0)
        # 法律上、年10日以上の有給休暇が付与される労働者が「年5日取得義務」の対象
        is_target = total_granted >= 10.0
        if is_target:
            target_staff_count += 1

        used_count = db.query(models.Shift).filter(
            models.Shift.user_id == u.id,
            models.Shift.date >= year_start,
            models.Shift.date <= year_end,
            models.Shift.shift_type == "PAID_LEAVE"
        ).count()

        used_days = float(used_count)
        remaining = max(0.0, total_granted - used_days)
        progress_pct = int(min(100, round((used_days / 5.0) * 100)))

        if not is_target:
            status_code = "ACHIEVED"
            msg = "年10日未満付与のため義務対象外"
        elif used_days >= 5.0:
            status_code = "ACHIEVED"
            msg = "年5日取得義務を達成しています"
            achieved_count += 1
        elif used_days >= 3.0:
            status_code = "IN_PROGRESS"
            msg = f"計画的取得中（あと{5.0 - used_days:.0f}日の取得が必要）"
            in_progress_count += 1
        else:
            status_code = "ACTION_REQUIRED"
            msg = f"要取得推進（あと{5.0 - used_days:.0f}日の取得が必要です）"
            action_required_count += 1

        staff_compliance.append(schemas.PaidLeaveComplianceUser(
            user_id=u.id,
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            total_granted=total_granted,
            used_days=used_days,
            remaining_days=remaining,
            legal_progress_percent=progress_pct,
            status=status_code,
            warning_message=msg
        ))

    return schemas.PaidLeaveComplianceResponse(
        year=target_year,
        total_target_staff=target_staff_count,
        achieved_count=achieved_count,
        in_progress_count=in_progress_count,
        action_required_count=action_required_count,
        staff=staff_compliance
    )

# --- フェーズ4: 全データ一括バックアップ（ZIP/CSV） ---
@router.get("/backup/export")
def export_all_data_zip(
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. users.csv
        u_out = io.StringIO()
        u_out.write('\ufeff')
        u_writer = csv.writer(u_out)
        u_writer.writerow([
            "ユーザーID", "ログインID", "氏名", "役職", "給与形態",
            "時給", "月給", "有休付与日数", "有休繰越日数", "有休基準日",
            "勤務可能曜日", "表示カラー", "有効フラグ", "登録日時"
        ])
        users = db.query(models.User).order_by(models.User.id.asc()).all()
        user_map = {u.id: u.full_name for u in users}
        for u in users:
            u_writer.writerow([
                u.id, u.username, u.full_name, u.role, u.wage_type,
                u.hourly_wage, u.monthly_salary, u.paid_leave_granted, u.paid_leave_carried,
                u.paid_leave_base_date.isoformat() if u.paid_leave_base_date else "",
                u.work_days or "", u.color or "", 1 if u.is_active else 0,
                u.created_at.isoformat() if u.created_at else ""
            ])
        zf.writestr("users.csv", u_out.getvalue().encode("utf-8-sig"))

        # 2. shifts.csv
        s_out = io.StringIO()
        s_out.write('\ufeff')
        s_writer = csv.writer(s_out)
        s_writer.writerow([
            "シフトID", "ユーザーID", "スタッフ氏名", "日付",
            "開始時刻", "終了時刻", "休憩時間(分)", "シフト区分", "備考"
        ])
        shifts = db.query(models.Shift).order_by(models.Shift.date.asc(), models.Shift.id.asc()).all()
        for s in shifts:
            s_writer.writerow([
                s.id, s.user_id, user_map.get(s.user_id, ""), s.date.isoformat(),
                s.start_time.strftime("%H:%M") if s.start_time else "",
                s.end_time.strftime("%H:%M") if s.end_time else "",
                s.break_minutes or 0, s.shift_type, s.note or ""
            ])
        zf.writestr("shifts.csv", s_out.getvalue().encode("utf-8-sig"))

        # 3. time_records.csv
        t_out = io.StringIO()
        t_out.write('\ufeff')
        t_writer = csv.writer(t_out)
        t_writer.writerow([
            "勤怠ID", "ユーザーID", "スタッフ氏名", "日付",
            "出勤日時", "退勤日時", "休憩開始", "休憩終了",
            "総休憩時間(分)", "総実労働時間(分)", "ステータス", "修正フラグ", "備考"
        ])
        records = db.query(models.TimeRecord).order_by(models.TimeRecord.date.asc(), models.TimeRecord.id.asc()).all()
        for r in records:
            t_writer.writerow([
                r.id, r.user_id, user_map.get(r.user_id, ""), r.date.isoformat(),
                r.clock_in.strftime("%Y-%m-%d %H:%M:%S") if r.clock_in else "",
                r.clock_out.strftime("%Y-%m-%d %H:%M:%S") if r.clock_out else "",
                r.break_start.strftime("%Y-%m-%d %H:%M:%S") if r.break_start else "",
                r.break_end.strftime("%Y-%m-%d %H:%M:%S") if r.break_end else "",
                r.total_break_minutes or 0, r.total_work_minutes or 0,
                r.status, 1 if r.is_corrected else 0, r.note or ""
            ])
        zf.writestr("time_records.csv", t_out.getvalue().encode("utf-8-sig"))

        # 4. shift_requests.csv
        sr_out = io.StringIO()
        sr_out.write('\ufeff')
        sr_writer = csv.writer(sr_out)
        sr_writer.writerow([
            "希望休ID", "ユーザーID", "スタッフ氏名", "希望日",
            "区分", "理由", "審査状況", "管理者コメント", "申請日時"
        ])
        s_requests = db.query(models.ShiftRequest).order_by(models.ShiftRequest.date.asc()).all()
        for sr in s_requests:
            sr_writer.writerow([
                sr.id, sr.user_id, user_map.get(sr.user_id, ""), sr.date.isoformat(),
                sr.request_type, sr.reason or "", sr.status, sr.admin_comment or "",
                sr.created_at.isoformat() if sr.created_at else ""
            ])
        zf.writestr("shift_requests.csv", sr_out.getvalue().encode("utf-8-sig"))

        # 5. correction_requests.csv
        cr_out = io.StringIO()
        cr_out.write('\ufeff')
        cr_writer = csv.writer(cr_out)
        cr_writer.writerow([
            "打刻修正ID", "ユーザーID", "スタッフ氏名", "対象日",
            "修正希望出勤", "修正希望退勤", "修正休憩(分)", "理由", "審査状況", "管理者コメント", "申請日時"
        ])
        c_requests = db.query(models.CorrectionRequest).order_by(models.CorrectionRequest.target_date.asc()).all()
        for cr in c_requests:
            cr_writer.writerow([
                cr.id, cr.user_id, user_map.get(cr.user_id, ""), cr.target_date.isoformat(),
                cr.requested_clock_in.strftime("%Y-%m-%d %H:%M:%S") if cr.requested_clock_in else "",
                cr.requested_clock_out.strftime("%Y-%m-%d %H:%M:%S") if cr.requested_clock_out else "",
                cr.requested_break_minutes or 0, cr.reason or "", cr.status, cr.admin_comment or "",
                cr.created_at.isoformat() if cr.created_at else ""
            ])
        zf.writestr("correction_requests.csv", cr_out.getvalue().encode("utf-8-sig"))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"shift_kintai_backup_{timestamp}.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

