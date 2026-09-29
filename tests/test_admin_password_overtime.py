"""
tests/test_admin_password_overtime.py
管理者メニューにおける「パスワード残業申請」機能および承認フローのテスト
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
import models


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_client():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "miyake",
        "password": "admin123"
    })
    assert r.status_code == 200
    return c


@pytest.fixture
def staff_user():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "kobayashi").first()
        return user
    finally:
        db.close()


def test_admin_overtime_apply_with_staff_password(admin_client, staff_user):
    """スタッフ本人のパスワードによる残業申請が成功し、承認待ちリストに登録されること"""
    db = SessionLocal()
    try:
        # 事前クリーンアップ
        db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == staff_user.id,
            models.LeaveRequest.date == date(2026, 11, 10)
        ).delete()
        db.commit()
    finally:
        db.close()

    res = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "kobayashi1234",
        "date": "2026-11-10",
        "overtime_hours": 1.5,
        "reason": "急患対応・処方箋集中のため残業"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "小林" in data["message"]
    req_id = data["request_id"]

    # DBのレコード確認
    db = SessionLocal()
    try:
        req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == req_id).first()
        assert req is not None
        assert req.leave_type == "OVERTIME"
        assert req.status == models.RequestStatus.PENDING
        assert req.overtime_hours == 1.5
        assert "急患対応" in req.reason
    finally:
        db.close()


def test_admin_overtime_apply_with_admin_password(admin_client, staff_user):
    """管理者パスワードによる代理申請も正当な認証として受け付けられること"""
    res = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "admin123",
        "date": "2026-11-11",
        "overtime_hours": 2.0,
        "reason": "月末棚卸業務のため"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["overtime_hours"] == 2.0


def test_admin_overtime_apply_wrong_password_rejected(admin_client, staff_user):
    """誤ったパスワードの場合は400エラーで拒否されること（本人認証）"""
    res = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "wrong_password_xyz",
        "date": "2026-11-12",
        "overtime_hours": 1.0,
        "reason": "テスト理由"
    })
    assert res.status_code == 400
    assert "パスワードが正しくありません" in res.json()["detail"]


def test_admin_overtime_apply_validation(admin_client, staff_user):
    """残業時間や理由が不正な場合は400エラーで適切に弾かれること"""
    # 理由なし
    res_no_reason = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "kobayashi1234",
        "date": "2026-11-13",
        "overtime_hours": 1.0,
        "reason": "   "
    })
    assert res_no_reason.status_code == 400
    assert "残業内容（理由）" in res_no_reason.json()["detail"]

    # 時間が0
    res_zero_hours = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "kobayashi1234",
        "date": "2026-11-13",
        "overtime_hours": 0,
        "reason": "業務対応"
    })
    assert res_zero_hours.status_code == 400
    assert "残業時間" in res_zero_hours.json()["detail"]


def test_admin_overtime_full_approval_flow(admin_client, staff_user):
    """申請後に管理者がそれを見て承認ボタンを押すフローの完全検証"""
    target_date = "2026-11-20"
    db = SessionLocal()
    try:
        # 当日のシフトを作成しておく
        db.query(models.Shift).filter(
            models.Shift.user_id == staff_user.id,
            models.Shift.date == date(2026, 11, 20)
        ).delete()
        s = models.Shift(
            user_id=staff_user.id,
            date=date(2026, 11, 20),
            shift_type=models.ShiftType.FULL,
            note="通常勤務"
        )
        db.add(s)
        db.commit()
    finally:
        db.close()

    # 1. 管理者メニューからパスワード残業申請
    apply_res = admin_client.post("/api/admin/overtime-apply", json={
        "user_id": staff_user.id,
        "password": "kobayashi1234",
        "date": target_date,
        "overtime_hours": 1.5,
        "reason": "調剤監査・混雑対応のため"
    })
    assert apply_res.status_code == 200
    req_id = apply_res.json()["request_id"]

    # 2. 管理者の申請一覧取得で申請を確認
    list_res = admin_client.get("/api/admin/leave-requests")
    assert list_res.status_code == 200
    reqs = list_res.json()
    matched = [r for r in reqs if r["id"] == req_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "PENDING"
    assert matched[0]["leave_type"] == "OVERTIME"
    assert matched[0]["overtime_hours"] == 1.5
    assert "調剤監査" in matched[0]["reason"]

    # 3. 管理者が「承認する」ボタンを押下
    review_res = admin_client.post(f"/api/admin/leave-requests/{req_id}/review", json={
        "status": "APPROVED",
        "admin_note": "お疲れ様でした。承認しました。"
    })
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "APPROVED"

    # 4. シフトのnoteに残業承認が記載され、スタッフへのプライベートメッセージが生成されていること
    db = SessionLocal()
    try:
        updated_shift = db.query(models.Shift).filter(
            models.Shift.user_id == staff_user.id,
            models.Shift.date == date(2026, 11, 20)
        ).first()
        assert updated_shift is not None
        assert "[残業承認: 1.5h]" in updated_shift.note

        # スタッフ宛ての最新メッセージ確認
        msg = db.query(models.Message).filter(
            models.Message.to_user_id == staff_user.id
        ).order_by(models.Message.created_at.desc()).first()
        assert msg is not None
        assert "残業申請" in msg.content
        assert "承認" in msg.content
        assert "お疲れ様でした" in msg.content
    finally:
        db.close()


def test_staff_condition_password_update(admin_client, staff_user):
    """スタッフ勤務条件編集モーダルからのパスワード変更が正常に動作すること"""
    db = SessionLocal()
    try:
        orig_pw_hash = staff_user.password_hash
    finally:
        db.close()

    # パスワードを更新
    res = admin_client.put(f"/api/admin/staff/{staff_user.id}/condition", json={
        "new_password": "kobayashi_newpass"
    })
    assert res.status_code == 200

    # 新パスワードでログインできること
    login_client = TestClient(app)
    login_res = login_client.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi_newpass"
    })
    assert login_res.status_code == 200

    # 元のパスワードに戻す（他テストへの影響防止）
    admin_client.put(f"/api/admin/staff/{staff_user.id}/condition", json={
        "new_password": "kobayashi1234"
    })
