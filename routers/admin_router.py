import calendar
import csv
from datetime import date, datetime, time
import io
import random
from typing import List, Optional
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from auth import get_admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ShiftUpdateRequest(BaseModel):
    user_id: int
    date: str  # YYYY-MM-DD
    shift_type: str  # FULL/AM/PM/FIRST/SECOND/OFF


class AutoGenerateRequest(BaseModel):
    year: int
    month: int
    overwrite: bool = True


class MessageSendRequest(BaseModel):
    to_user_id: int
    content: str


class LeaveReviewRequest(BaseModel):
    status: str  # APPROVED / REJECTED
    admin_note: Optional[str] = ""


class BatchFillTimeRecordsRequest(BaseModel):
    user_id: int
    year: int
    month: int
    overwrite_existing: bool = False  # False: 未打刻のみ補完, True: 当月すべて再生成


class SingleTimeRecordUpdateRequest(BaseModel):
    user_id: int
    date: str  # YYYY-MM-DD
    clock_in: Optional[str] = None   # "HH:MM"
    clock_out: Optional[str] = None  # "HH:MM"
    break_minutes: Optional[int] = 60
    clear: bool = False


@router.get("/shifts/monthly")
def get_admin_monthly_shifts(
    year: int,
    month: int,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """月間シフト一覧取得（管理者画面用）"""
    _, days_in_month = calendar.monthrange(year, month)
    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.position, models.User.id).all()
    shifts = db.query(models.Shift).filter(
        models.Shift.date >= date(year, month, 1),
        models.Shift.date <= date(year, month, days_in_month)
    ).all()

    shift_map = {}
    for s in shifts:
        shift_map[f"{s.date.isoformat()}_{s.user_id}"] = {
            "id": s.id,
            "shift_type": s.shift_type.value,
            "shift_label": s.shift_label,
            "time_range": s.time_range,
        }

    return {
        "year": year,
        "month": month,
        "days_in_month": days_in_month,
        "users": [
            {
                "id": u.id,
                "full_name": u.full_name,
                "position": u.position.value,
                "position_label": u.position_label,
                "employment_type": u.employment_type.value,
                "color": u.position_color,
                "default_shift": u.default_shift.value,
                "fixed_off_weekdays": u.fixed_off_weekdays,
            }
            for u in users
        ],
        "shifts": shift_map
    }


@router.post("/shifts/single")
def update_single_shift(
    req: ShiftUpdateRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """シフト1件の登録・更新・削除"""
    shift_date = date.fromisoformat(req.date)
    shift_type_enum = models.ShiftType(req.shift_type)

    existing = db.query(models.Shift).filter(
        models.Shift.user_id == req.user_id,
        models.Shift.date == shift_date
    ).first()

    if shift_type_enum == models.ShiftType.OFF:
        if existing:
            db.delete(existing)
            db.commit()
        return {"success": True, "action": "deleted"}

    if existing:
        existing.shift_type = shift_type_enum
    else:
        new_shift = models.Shift(
            user_id=req.user_id,
            date=shift_date,
            shift_type=shift_type_enum,
            note=""
        )
        db.add(new_shift)

    db.commit()
    return {"success": True, "action": "updated"}


from shift_rules import calculate_shift_type

@router.post("/shifts/auto-generate")
def auto_generate_shifts(
    req: AutoGenerateRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    就業時間体系（出勤か休日のみ）に応じた月間シフト一括自動生成
    ※ 日曜・祝日: 全員一斉休み
    ※ 土曜日: 出勤者全員「午前診 (AM: 9:00〜13:00)」
    ※ 木曜日: 出勤者全員「午前だけ (AM: 9:00〜13:00)」
    ※ 月・火・水・金: 出勤者全員「全日 (FULL: 9:00〜19:00)」
    ※ 各スタッフの固定定休日は休日判定
    """
    _, days_in_month = calendar.monthrange(req.year, req.month)
    users = db.query(models.User).filter(models.User.is_active == True).all()

    if req.overwrite:
        db.query(models.Shift).filter(
            models.Shift.date >= date(req.year, req.month, 1),
            models.Shift.date <= date(req.year, req.month, days_in_month)
        ).delete()

    generated_count = 0
    for day in range(1, days_in_month + 1):
        d = date(req.year, req.month, day)
        for u in users:
            st = calculate_shift_type(u, d)
            if st is None:
                continue

            shift = models.Shift(
                user_id=u.id,
                date=d,
                shift_type=st,
                note=""
            )
            db.add(shift)
            generated_count += 1

    db.commit()
    return {
        "success": True,
        "generated_count": generated_count,
        "message": f"{req.year}年{req.month}月の一括シフトを作成しました（{generated_count}件）"
    }


@router.get("/leave-requests")
def get_leave_requests(
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """届いた休暇申請一覧（管理者のみ閲覧可能・他スタッフからは遮断）"""
    reqs = db.query(models.LeaveRequest).order_by(models.LeaveRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": r.user.full_name,
            "position_label": r.user.position_label,
            "date": r.date.isoformat(),
            "request_type": r.request_type,
            "leave_type": r.leave_type,
            "reason": r.reason,
            "status": r.status.value,
            "admin_note": r.admin_note,
            "created_at": r.created_at.strftime("%Y/%m/%d %H:%M"),
        }
        for r in reqs
    ]


@router.post("/leave-requests/{req_id}/review")
def review_leave_request(
    req_id: int,
    data: LeaveReviewRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """休暇申請の個別承認・却下（プライベート通知対応）"""
    item = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == req_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申請が見つかりません")

    new_status = models.RequestStatus(data.status)
    item.status = new_status
    item.admin_note = data.admin_note or ""

    # 承認された場合はシフトを自動でOFFまたは有休に更新
    if new_status == models.RequestStatus.APPROVED:
        existing_shift = db.query(models.Shift).filter(
            models.Shift.user_id == item.user_id,
            models.Shift.date == item.date
        ).first()
        if existing_shift:
            db.delete(existing_shift)

    # スタッフへの個別メッセージを自動送信してプライベート通知
    status_label = "承認" if new_status == models.RequestStatus.APPROVED else "却下"
    msg_content = f"【申請の確認】{item.date.strftime('%m月%d日')}の休暇申請が{status_label}されました。"
    if data.admin_note:
        msg_content += f"\nメッセージ: {data.admin_note}"

    msg = models.Message(
        from_user_id=admin.id,
        to_user_id=item.user_id,
        content=msg_content,
        is_read=False
    )
    db.add(msg)
    db.commit()

    return {"success": True, "status": item.status.value}


@router.post("/messages")
def send_private_message(
    data: MessageSendRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """管理者からスタッフ個人へのプライベート個別メッセージ送信"""
    recipient = db.query(models.User).filter(models.User.id == data.to_user_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="送信先スタッフが見つかりません")

    msg = models.Message(
        from_user_id=admin.id,
        to_user_id=data.to_user_id,
        content=data.content,
        is_read=False
    )
    db.add(msg)
    db.commit()
    return {"success": True, "message_id": msg.id}


# --- 1. スタッフ勤務条件・時間設定（雇用形態・定休日・シフト区分） ---
@router.get("/staff/conditions", response_model=schemas.StaffConditionsResponse)
def get_staff_conditions(
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """全スタッフの勤務条件（シフト区分・定休曜日・時給・有休）一覧"""
    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.position, models.User.id).all()
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]

    items = []
    shift_labels = {
        models.ShiftType.FULL: "全日",
        models.ShiftType.AM: "午前診",
        models.ShiftType.PM: "午後診",
        models.ShiftType.FIRST: "前半",
        models.ShiftType.SECOND: "後半",
        models.ShiftType.OFF: "休み",
    }

    for u in users:
        off_days = [x.strip() for x in (u.fixed_off_weekdays or "6").split(",") if x.strip()]
        off_labels = [weekday_names[int(x)] for x in off_days if x.isdigit() and 0 <= int(x) <= 6]

        items.append(schemas.StaffConditionItem(
            id=u.id,
            full_name=u.full_name,
            username=u.username,
            position=u.position.value,
            position_label=u.position_label,
            employment_type=u.employment_type.value,
            default_shift=u.default_shift.value,
            default_shift_label=shift_labels.get(u.default_shift, ""),
            shift_time_range=u.shift_time_range,
            fixed_off_weekdays=u.fixed_off_weekdays or "6",
            fixed_off_labels=off_labels,
            color=u.evaluation_color or u.position_color,
            hourly_wage=u.hourly_wage or 0,
            paid_leave_remaining=u.paid_leave_remaining or 0.0,
            is_active=u.is_active
        ))
    return schemas.StaffConditionsResponse(staff=items)


@router.put("/staff/{user_id}/condition")
def update_staff_condition(
    user_id: int,
    data: schemas.StaffConditionUpdateRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """スタッフ個人の勤務条件（シフト区分・定休曜日・時給・有休）を更新保存"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="スタッフが見つかりません")

    if data.default_shift is not None:
        try:
            user.default_shift = models.ShiftType(data.default_shift)
        except ValueError:
            raise HTTPException(status_code=400, detail="無効なシフト区分です")

    if data.fixed_off_weekdays is not None:
        user.fixed_off_weekdays = data.fixed_off_weekdays

    if data.hourly_wage is not None:
        user.hourly_wage = max(0, data.hourly_wage)

    if data.paid_leave_remaining is not None:
        user.paid_leave_remaining = max(0.0, data.paid_leave_remaining)

    if data.employment_type is not None:
        try:
            user.employment_type = models.EmploymentType(data.employment_type)
        except ValueError:
            pass

    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "user_id": user.id,
        "full_name": user.full_name,
        "default_shift": user.default_shift.value,
        "fixed_off_weekdays": user.fixed_off_weekdays,
        "hourly_wage": user.hourly_wage,
        "paid_leave_remaining": user.paid_leave_remaining,
        "message": f"{user.full_name}さんの勤務条件を更新しました"
    }


# --- 2. シフト確定・LINE共有用テキスト生成 ---
@router.get("/shifts/share-text", response_model=schemas.ShiftShareTextResponse)
def get_shift_share_text(
    year: int = Query(default=None),
    month: int = Query(default=None),
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """月間確定シフトのグループLINE用一括テキスト ＆ スタッフ別個別テキスト生成"""
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    _, last_day = calendar.monthrange(target_year, target_month)
    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.position, models.User.id).all()
    shifts = db.query(models.Shift).filter(
        models.Shift.date >= date(target_year, target_month, 1),
        models.Shift.date <= date(target_year, target_month, last_day)
    ).all()

    shift_map = {}
    for s in shifts:
        shift_map[(s.date.day, s.user_id)] = s

    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]

    # 1. 全員分グループLINE用テキスト
    group_lines = [
        f"【リリー薬局】{target_year}年{target_month}月 シフト確定連絡",
        "いつもご勤務ありがとうございます。今月のシフト予定です。",
        "------------------------------------"
    ]
    for d in range(1, last_day + 1):
        dt = date(target_year, target_month, d)
        w = weekday_ja[dt.weekday()]
        working_names = []
        for u in users:
            s = shift_map.get((d, u.id))
            if s and s.shift_type != models.ShiftType.OFF:
                working_names.append(f"{u.full_name}({s.shift_label})")

        if working_names:
            group_lines.append(f"・{target_month}/{d}({w}): " + ", ".join(working_names))
        else:
            group_lines.append(f"・{target_month}/{d}({w}): 休局（日祝）")
    group_lines.append("------------------------------------")
    group_lines.append("※変更・希望等がありましたらお早めにお知らせください。")
    full_text = "\n".join(group_lines)

    # 2. スタッフ別テキスト
    by_staff = []
    for u in users:
        staff_lines = [
            f"【リリー薬局】{target_year}年{target_month}月 出勤予定（{u.full_name}さん）",
            "いつもありがとうございます！今月の出勤予定です。",
            "------------------------------------"
        ]
        work_count = 0
        for d in range(1, last_day + 1):
            dt = date(target_year, target_month, d)
            w = weekday_ja[dt.weekday()]
            s = shift_map.get((d, u.id))
            if s and s.shift_type != models.ShiftType.OFF:
                work_count += 1
                staff_lines.append(f"・{target_month}/{d}({w}): {s.shift_label} ({s.time_range})")
        staff_lines.append("------------------------------------")
        staff_lines.append(f"合計出勤日数: {work_count}日")
        staff_lines.append("今月も体調に気をつけてよろしくお願いいたします✨")

        by_staff.append(schemas.ShiftShareStaffText(
            user_id=u.id,
            user_name=u.full_name,
            days_count=work_count,
            text="\n".join(staff_lines)
        ))

    return schemas.ShiftShareTextResponse(
        year=target_year,
        month=target_month,
        full_text=full_text,
        by_staff=by_staff
    )


# --- 3. 全データ一括バックアップ（ZIP/BOM付きCSV） ---
@router.get("/backup/export")
def export_all_data_zip(
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """全スタッフ・全シフト・全勤怠履歴・全申請をExcel文字化け防止BOM付きCSVとしてZIP一括ダウンロード"""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. users.csv
        u_out = io.StringIO()
        u_out.write('\ufeff')
        u_writer = csv.writer(u_out)
        u_writer.writerow([
            "スタッフID", "ログインID", "氏名", "役職", "基本シフト",
            "定休日", "設定時給", "有休残日数", "有効フラグ", "登録日時"
        ])
        users = db.query(models.User).order_by(models.User.id.asc()).all()
        user_map = {u.id: u.full_name for u in users}
        for u in users:
            u_writer.writerow([
                u.id, u.username, u.full_name, u.position_label, u.default_shift.value,
                u.fixed_off_weekdays or "", u.hourly_wage or 0, u.paid_leave_remaining or 0.0,
                1 if u.is_active else 0, u.created_at.isoformat() if u.created_at else ""
            ])
        zf.writestr("users.csv", u_out.getvalue().encode("utf-8-sig"))

        # 2. shifts.csv
        s_out = io.StringIO()
        s_out.write('\ufeff')
        s_writer = csv.writer(s_out)
        s_writer.writerow([
            "シフトID", "スタッフID", "氏名", "日付", "シフト区分", "時間帯", "備考"
        ])
        shifts = db.query(models.Shift).order_by(models.Shift.date.asc(), models.Shift.id.asc()).all()
        for s in shifts:
            s_writer.writerow([
                s.id, s.user_id, user_map.get(s.user_id, ""), s.date.isoformat(),
                s.shift_label, s.time_range, s.note or ""
            ])
        zf.writestr("shifts.csv", s_out.getvalue().encode("utf-8-sig"))

        # 3. time_records.csv
        t_out = io.StringIO()
        t_out.write('\ufeff')
        t_writer = csv.writer(t_out)
        t_writer.writerow([
            "勤怠ID", "スタッフID", "氏名", "日付",
            "出勤時刻", "退勤時刻", "休憩開始", "休憩終了", "実働分数", "ステータス"
        ])
        records = db.query(models.TimeRecord).order_by(models.TimeRecord.date.asc(), models.TimeRecord.id.asc()).all()
        for r in records:
            t_writer.writerow([
                r.id, r.user_id, user_map.get(r.user_id, ""), r.date.isoformat(),
                r.clock_in.strftime("%H:%M") if r.clock_in else "",
                r.clock_out.strftime("%H:%M") if r.clock_out else "",
                r.break_start.strftime("%H:%M") if r.break_start else "",
                r.break_end.strftime("%H:%M") if r.break_end else "",
                r.work_minutes, r.status.value if r.status else ""
            ])
        zf.writestr("time_records.csv", t_out.getvalue().encode("utf-8-sig"))

        # 4. leave_requests.csv
        l_out = io.StringIO()
        l_out.write('\ufeff')
        l_writer = csv.writer(l_out)
        l_writer.writerow([
            "申請ID", "スタッフID", "氏名", "希望日", "区分", "休暇種別", "理由", "審査状況", "管理者メモ", "申請日時"
        ])
        l_requests = db.query(models.LeaveRequest).order_by(models.LeaveRequest.date.asc()).all()
        for lr in l_requests:
            l_writer.writerow([
                lr.id, lr.user_id, user_map.get(lr.user_id, ""), lr.date.isoformat(),
                lr.request_type, lr.leave_type, lr.reason or "", lr.status.value if lr.status else "",
                lr.admin_note or "", lr.created_at.isoformat() if lr.created_at else ""
            ])
        zf.writestr("leave_requests.csv", l_out.getvalue().encode("utf-8-sig"))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"lily_pharmacy_backup_{timestamp}.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# --- 4. 有給休暇 年5日取得義務コンプライアンス判定 ---
@router.get("/compliance/paid-leave", response_model=schemas.PaidLeaveComplianceResponse)
def get_paid_leave_compliance(
    year: int = Query(default=None),
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """労働基準法第39条第7項「年5日有休取得義務」の自動進捗判定"""
    target_year = year or date.today().year
    year_start = date(target_year, 1, 1)
    year_end = date(target_year, 12, 31)

    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.position, models.User.id).all()

    staff_compliance = []
    achieved_count = 0
    in_progress_count = 0
    action_required_count = 0
    target_staff_count = len(users)

    for u in users:
        used_count = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == u.id,
            models.LeaveRequest.date >= year_start,
            models.LeaveRequest.date <= year_end,
            models.LeaveRequest.leave_type == "PAID_LEAVE",
            models.LeaveRequest.status == models.RequestStatus.APPROVED
        ).count()

        used_days = float(used_count)
        remaining = max(0.0, (u.paid_leave_remaining or 0.0))
        progress_pct = int(min(100, round((used_days / 5.0) * 100)))

        if used_days >= 5.0:
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
            role=u.position_label,
            total_granted=5.0,
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


# --- 5. 小林・本間専用「リアル秒単位ゆらぎ」一括打刻支援 ＆ タイムカード機能 ---
def generate_realistic_minutes_time(shift_type: models.ShiftType):
    """
    現場の実態（毎日早く来て準備し、残業もして帰る）に即した完全ランダムな一桁分刻み＋秒単位の出退勤時刻を生成。
    電子タイムレコーダーの生ログと同様の自然なゆらぎ（秒まで完全再現）。
    返り値: (clock_in_time, clock_out_time, break_minutes)
    """
    if shift_type == models.ShiftType.OFF:
        return None, None, 0

    if shift_type == models.ShiftType.FIRST:
        # 前半: 定時 9:00〜18:00 (本間まや など)
        # 出勤: 8:46〜8:56 のランダムな一桁分、02〜58秒
        in_min = random.randint(46, 56)
        in_sec = random.randint(2, 58)
        # 退勤: 18:04〜18:22 のランダムな一桁分、02〜58秒
        out_min = random.randint(4, 22)
        out_sec = random.randint(2, 58)
        return time(8, in_min, in_sec), time(18, out_min, out_sec), 60

    elif shift_type == models.ShiftType.SECOND:
        # 後半: 定時 10:00〜19:00 (小林彩乃 など)
        in_min = random.randint(47, 56)
        in_sec = random.randint(2, 58)
        out_min = random.randint(4, 23)
        out_sec = random.randint(2, 58)
        return time(9, in_min, in_sec), time(19, out_min, out_sec), 60

    elif shift_type == models.ShiftType.AM:
        # 午前診: 定時 9:00〜13:00 (土曜・火曜/木曜など、休憩なし)
        in_min = random.randint(47, 55)
        in_sec = random.randint(2, 58)
        out_min = random.randint(3, 16)
        out_sec = random.randint(2, 58)
        return time(8, in_min, in_sec), time(13, out_min, out_sec), 0

    elif shift_type == models.ShiftType.PM:
        # 午後診: 定時 15:00〜19:00 (休憩なし)
        in_min = random.randint(48, 56)
        in_sec = random.randint(2, 58)
        out_min = random.randint(3, 18)
        out_sec = random.randint(2, 58)
        return time(14, in_min, in_sec), time(19, out_min, out_sec), 0

    elif shift_type == models.ShiftType.FULL:
        # 全日: 定時 9:00〜19:00
        in_min = random.randint(46, 55)
        in_sec = random.randint(2, 58)
        out_min = random.randint(4, 24)
        out_sec = random.randint(2, 58)
        return time(8, in_min, in_sec), time(19, out_min, out_sec), 60

    return None, None, 0


@router.get("/time-records/monthly")
def get_admin_monthly_time_records(
    user_id: int,
    year: int,
    month: int,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """指定スタッフの月間タイムカードデータ取得（日別出退勤・実労働時間）"""
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="スタッフが見つかりません")

    _, days_in_month = calendar.monthrange(year, month)
    shifts = db.query(models.Shift).filter(
        models.Shift.user_id == user_id,
        models.Shift.date >= date(year, month, 1),
        models.Shift.date <= date(year, month, days_in_month)
    ).all()
    shift_map = {s.date.day: s for s in shifts}

    records = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == user_id,
        models.TimeRecord.date >= date(year, month, 1),
        models.TimeRecord.date <= date(year, month, days_in_month)
    ).all()
    record_map = {r.date.day: r for r in records}

    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    days_data = []

    total_work_minutes = 0
    total_worked_days = 0
    total_overtime_minutes = 0

    for day in range(1, days_in_month + 1):
        dt = date(year, month, day)
        wd = dt.weekday()
        s = shift_map.get(day)
        r = record_map.get(day)

        shift_type = s.shift_type.value if s else "OFF"
        shift_label = s.shift_label if s else "休"
        time_range = s.time_range if s else ""

        clock_in_str = r.clock_in.strftime("%H:%M:%S") if (r and r.clock_in) else ""
        clock_out_str = r.clock_out.strftime("%H:%M:%S") if (r and r.clock_out) else ""

        break_mins = 0
        work_mins = 0
        if r and r.clock_in and r.clock_out:
            work_mins = r.work_minutes
            if r.break_start and r.break_end:
                bs = datetime.combine(dt, r.break_start)
                be = datetime.combine(dt, r.break_end)
                break_mins = int((be - bs).total_seconds() / 60)
            elif shift_type in ["FULL", "FIRST", "SECOND"]:
                break_mins = 60

            total_work_minutes += work_mins
            total_worked_days += 1
            if work_mins > 480:
                total_overtime_minutes += (work_mins - 480)

        work_hours_str = f"{work_mins // 60}時間{work_mins % 60:02d}分" if work_mins > 0 else "-"

        days_data.append({
            "day": day,
            "date": dt.isoformat(),
            "weekday": wd,
            "weekday_label": weekday_names[wd],
            "is_weekend": (wd == 6 or wd == 5),
            "shift_type": shift_type,
            "shift_label": shift_label,
            "time_range": time_range,
            "clock_in": clock_in_str,
            "clock_out": clock_out_str,
            "break_minutes": break_mins,
            "work_minutes": work_mins,
            "work_hours_str": work_hours_str,
        })

    return {
        "user_id": target_user.id,
        "full_name": target_user.full_name,
        "position_label": target_user.position_label,
        "year": year,
        "month": month,
        "days": days_data,
        "summary": {
            "worked_days": total_worked_days,
            "total_work_minutes": total_work_minutes,
            "total_work_hours": round(total_work_minutes / 60.0, 1),
            "total_work_hours_str": f"{total_work_minutes // 60}時間{total_work_minutes % 60:02d}分",
            "overtime_minutes": total_overtime_minutes,
            "overtime_hours": round(total_overtime_minutes / 60.0, 1),
            "overtime_hours_str": f"{total_overtime_minutes // 60}時間{total_overtime_minutes % 60:02d}分",
        }
    }


@router.post("/time-records/batch-fill")
def batch_fill_time_records(
    req: BatchFillTimeRecordsRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """小林・本間専用：リアル一桁分刻みで当月の出退勤打刻を一括自動生成（ログなし完全自然打刻）"""
    target_user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="スタッフが見つかりません")

    _, days_in_month = calendar.monthrange(req.year, req.month)
    shifts = db.query(models.Shift).filter(
        models.Shift.user_id == req.user_id,
        models.Shift.date >= date(req.year, req.month, 1),
        models.Shift.date <= date(req.year, req.month, days_in_month)
    ).all()
    shift_map = {s.date: s for s in shifts}

    filled_count = 0
    for day in range(1, days_in_month + 1):
        dt = date(req.year, req.month, day)
        s = shift_map.get(dt)
        if not s or s.shift_type == models.ShiftType.OFF:
            continue

        existing = db.query(models.TimeRecord).filter(
            models.TimeRecord.user_id == req.user_id,
            models.TimeRecord.date == dt
        ).first()

        if existing and not req.overwrite_existing:
            if existing.clock_in and existing.clock_out:
                continue

        c_in, c_out, b_mins = generate_realistic_minutes_time(s.shift_type)
        if not c_in or not c_out:
            continue

        if not existing:
            existing = models.TimeRecord(
                user_id=req.user_id,
                date=dt,
                status=models.ClockStatus.DONE
            )
            db.add(existing)

        existing.clock_in = c_in
        existing.clock_out = c_out
        if b_mins > 0:
            existing.break_start = time(13, 0)
            existing.break_end = time(14, 0)
        else:
            existing.break_start = None
            existing.break_end = None
        existing.status = models.ClockStatus.DONE
        filled_count += 1

    db.commit()
    return {
        "success": True,
        "filled_count": filled_count,
        "message": f"{target_user.full_name}さんの{req.year}年{req.month}月タイムカードをリアル秒単位ゆらぎで一括生成しました（{filled_count}日分）"
    }


@router.put("/time-records/single")
def update_single_time_record(
    req: SingleTimeRecordUpdateRequest,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """秒単位対応の手動打刻修正（ログなし・本人が押したのと同じクリーン保存）"""
    target_date = date.fromisoformat(req.date)
    record = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == req.user_id,
        models.TimeRecord.date == target_date
    ).first()

    if req.clear:
        if record:
            db.delete(record)
            db.commit()
        return {"success": True, "action": "cleared"}

    if not record:
        record = models.TimeRecord(
            user_id=req.user_id,
            date=target_date,
            status=models.ClockStatus.DONE
        )
        db.add(record)

    if req.clock_in:
        parts = req.clock_in.strip().split(":")
        if len(parts) >= 3:
            record.clock_in = time(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            # 秒が省略された場合は自然なランダム秒を付与してリアルタイムレコーダー感を維持
            record.clock_in = time(int(parts[0]), int(parts[1]), random.randint(2, 58))
        else:
            record.clock_in = None
    else:
        record.clock_in = None

    if req.clock_out:
        parts = req.clock_out.strip().split(":")
        if len(parts) >= 3:
            record.clock_out = time(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            record.clock_out = time(int(parts[0]), int(parts[1]), random.randint(2, 58))
        else:
            record.clock_out = None
    else:
        record.clock_out = None

    if (req.break_minutes or 0) > 0:
        record.break_start = time(13, 0)
        record.break_end = time(13 + (req.break_minutes // 60), req.break_minutes % 60)
    else:
        record.break_start = None
        record.break_end = None

    record.status = models.ClockStatus.DONE
    db.commit()
    return {"success": True, "action": "saved"}


@router.get("/time-records/export-csv")
def export_timecard_csv(
    user_id: int,
    year: int,
    month: int,
    admin: models.User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """指定スタッフの月間タイムカード出勤簿をBOM付きCSVとして直接ダウンロード"""
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="スタッフが見つかりません")

    _, days_in_month = calendar.monthrange(year, month)
    shifts = db.query(models.Shift).filter(
        models.Shift.user_id == user_id,
        models.Shift.date >= date(year, month, 1),
        models.Shift.date <= date(year, month, days_in_month)
    ).all()
    shift_map = {s.date.day: s for s in shifts}

    records = db.query(models.TimeRecord).filter(
        models.TimeRecord.user_id == user_id,
        models.TimeRecord.date >= date(year, month, 1),
        models.TimeRecord.date <= date(year, month, days_in_month)
    ).all()
    record_map = {r.date.day: r for r in records}

    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow([f"【リリー薬局】勤務実績出勤簿（タイムカード）"])
    writer.writerow([f"氏名: {target_user.full_name}", f"役職: {target_user.position_label}", f"対象年月: {year}年{month}月分"])
    writer.writerow([])
    writer.writerow(["日付", "曜日", "シフト区分", "出勤時刻", "退勤時刻", "休憩時間(分)", "実労働時間", "備考"])

    total_work_minutes = 0
    total_worked_days = 0

    for day in range(1, days_in_month + 1):
        dt = date(year, month, day)
        wd = dt.weekday()
        s = shift_map.get(day)
        r = record_map.get(day)

        shift_label = s.shift_label if s else "休"
        cin = r.clock_in.strftime("%H:%M:%S") if (r and r.clock_in) else ""
        cout = r.clock_out.strftime("%H:%M:%S") if (r and r.clock_out) else ""

        b_min = 0
        w_str = ""
        if r and r.clock_in and r.clock_out:
            w_min = r.work_minutes
            if r.break_start and r.break_end:
                bs = datetime.combine(dt, r.break_start)
                be = datetime.combine(dt, r.break_end)
                b_min = int((be - bs).total_seconds() / 60)
            elif s and s.shift_type in [models.ShiftType.FULL, models.ShiftType.FIRST, models.ShiftType.SECOND]:
                b_min = 60
            w_str = f"{w_min // 60}:{w_min % 60:02d}"
            total_work_minutes += w_min
            total_worked_days += 1

        writer.writerow([
            dt.strftime("%Y/%m/%d"),
            weekday_names[wd],
            shift_label,
            cin,
            cout,
            b_min if b_min > 0 else "",
            w_str,
            ""
        ])

    writer.writerow([])
    writer.writerow(["合計出勤日数", f"{total_worked_days}日", "総実労働時間", f"{total_work_minutes // 60}時間{total_work_minutes % 60:02d}分 ({round(total_work_minutes / 60.0, 1)}時間)"])

    filename = f"lily_timecard_{target_user.username}_{year}_{month:02d}.csv"
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
