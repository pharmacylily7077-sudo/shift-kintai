import calendar
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
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
    固定休日（日祝休日・火曜休み・木曜休みなど）と個別シフトルールに応じた月間一括自動生成
    ※ 日曜・祝日は全員一斉休み
    ※ 土曜日は全員午前診 (AM)
    ※ 本間は木曜日午前診 (AM)
    ※ 小林は火曜日は午前診 (AM)
    ※ 家田、寺内、山中、本間は火曜日休み
    ※ 小林は木曜日休み
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
