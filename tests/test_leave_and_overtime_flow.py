"""
tests/test_leave_and_overtime_flow.py
休日申請のシフト自動反映・一括自動生成保護、および残業申請（理由必須・管理者承認制）の検証
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
def staff_client():
    # 小林 彩乃
    c = TestClient(app)
    r = c.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi1234"
    })
    assert r.status_code == 200
    return c

def test_overtime_validation_and_approval(admin_client, staff_client):
    """残業申請の理由必須バリデーションと管理者承認フローのテスト"""
    # 1. 理由が空の残業申請 -> 400エラー
    r_empty_reason = staff_client.post("/api/me/leave-requests", json={
        "date": "2026-10-15",
        "leave_type": "OVERTIME",
        "overtime_hours": 1.5,
        "reason": "   "
    })
    assert r_empty_reason.status_code == 400
    assert "理由の入力が必須" in r_empty_reason.json()["detail"]

    # 2. 残業時間が未指定の残業申請 -> 400エラー
    r_no_hours = staff_client.post("/api/me/leave-requests", json={
        "date": "2026-10-15",
        "leave_type": "OVERTIME",
        "overtime_hours": 0,
        "reason": "急患対応のため"
    })
    assert r_no_hours.status_code == 400
    assert "残業予定時間" in r_no_hours.json()["detail"]

    # 3. 正常な残業申請
    r_success = staff_client.post("/api/me/leave-requests", json={
        "date": "2026-10-15",
        "leave_type": "OVERTIME",
        "overtime_hours": 2.0,
        "reason": "急患対応・処方箋集中のため"
    })
    assert r_success.status_code == 200
    req_id = r_success.json()["id"]

    # 4. 管理者画面で残業申請一覧を確認
    r_list = admin_client.get("/api/admin/leave-requests")
    assert r_list.status_code == 200
    reqs = r_list.json()
    target_req = next((r for r in reqs if r["id"] == req_id), None)
    assert target_req is not None
    assert target_req["leave_type"] == "OVERTIME"
    assert target_req["overtime_hours"] == 2.0
    assert "急患対応" in target_req["reason"]
    assert target_req["status"] == "PENDING"

    # 5. 管理者が残業申請を承認
    r_review = admin_client.post(f"/api/admin/leave-requests/{req_id}/review", json={
        "status": "APPROVED",
        "admin_note": "お疲れ様でした。承認します。"
    })
    assert r_review.status_code == 200
    assert r_review.json()["status"] == "APPROVED"

    # 6. スタッフマイルームでメッセージ受信と申請履歴を確認
    r_my_reqs = staff_client.get("/api/me/leave-requests")
    assert r_my_reqs.status_code == 200
    my_target = next((r for r in r_my_reqs.json() if r["id"] == req_id), None)
    assert my_target["status"] == "APPROVED"

    r_msgs = staff_client.get("/api/me/messages")
    assert r_msgs.status_code == 200
    assert any("残業申請（2.0時間）が承認" in m["content"] for m in r_msgs.json())


def test_leave_approval_and_auto_generate_protection(admin_client, staff_client, client):
    """
    休日申請（有休・希望休）がシフトに即時反映され、
    その後のシフト一括自動生成（overwrite=True）でも消去されず100%保護されることの検証
    """
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "kobayashi").first()
        user_id = user.id
        initial_paid_leave = user.paid_leave_remaining or 10.0
        user.paid_leave_remaining = initial_paid_leave
        db.commit()
    finally:
        db.close()

    target_month_year = (2026, 12)
    # 2026年12月8日（火曜日: 小林さんの通常出勤日）を有休申請
    paid_leave_date = "2026-12-08"
    # 2026年12月9日（水曜日: 小林さんの通常出勤日）を希望休申請
    hope_off_date = "2026-12-09"

    # 1. スタッフから有給休暇の申請
    r_pl = staff_client.post("/api/me/leave-requests", json={
        "date": paid_leave_date,
        "leave_type": "PAID_LEAVE",
        "reason": "私用のため有休希望"
    })
    assert r_pl.status_code == 200
    pl_id = r_pl.json()["id"]

    # 2. スタッフから希望休の申請
    r_off = staff_client.post("/api/me/leave-requests", json={
        "date": hope_off_date,
        "leave_type": "OFF",
        "reason": "法事のため希望休"
    })
    assert r_off.status_code == 200
    off_id = r_off.json()["id"]

    # 3. 管理者が双方を承認
    r_rev_pl = admin_client.post(f"/api/admin/leave-requests/{pl_id}/review", json={
        "status": "APPROVED",
        "admin_note": "有休承認しました"
    })
    assert r_rev_pl.status_code == 200

    r_rev_off = admin_client.post(f"/api/admin/leave-requests/{off_id}/review", json={
        "status": "APPROVED",
        "admin_note": "希望休了解です"
    })
    assert r_rev_off.status_code == 200

    # 4. 承認後、シフトテーブルおよび有休残日数に即時反映されているか確認
    db = SessionLocal()
    try:
        pl_shift = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 8)
        ).first()
        assert pl_shift is not None
        assert pl_shift.shift_type == models.ShiftType.PAID_LEAVE
        assert pl_shift.shift_label == "有休"

        off_shift = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 9)
        ).first()
        assert off_shift is not None
        assert off_shift.shift_type == models.ShiftType.HOPE_OFF
        assert off_shift.shift_label == "希休"

        # 有休残日数が1.0日減算されていること
        refreshed_user = db.query(models.User).filter(models.User.id == user_id).first()
        assert refreshed_user.paid_leave_remaining == initial_paid_leave - 1.0
    finally:
        db.close()

    # 5. カレンダーから直接、手動で12月11日を「有休」に設定（マス目クリック）
    r_manual = admin_client.post("/api/admin/shifts/single", json={
        "user_id": user_id,
        "date": "2026-12-11",
        "shift_type": "PAID_LEAVE"
    })
    assert r_manual.status_code == 200

    # 6. ★最重要★ 管理画面から「2026年12月の一括自動生成（overwrite=True）」を実行！
    r_gen = admin_client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 12,
        "overwrite": True
    })
    assert r_gen.status_code == 200
    assert r_gen.json()["success"] is True

    # 7. 自動生成後も、承認済み有休（8日）、承認済み希望休（9日）、手動設定有休（11日）が完全に保護されていること！
    db = SessionLocal()
    try:
        s8 = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 8)
        ).first()
        assert s8 is not None, "12月8日の有休が消えています！"
        assert s8.shift_type == models.ShiftType.PAID_LEAVE, f"12月8日が{s8.shift_type}で上書きされています！"

        s9 = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 9)
        ).first()
        assert s9 is not None, "12月9日の希望休が消えています！"
        assert s9.shift_type == models.ShiftType.HOPE_OFF, f"12月9日が{s9.shift_type}で上書きされています！"

        s11 = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 11)
        ).first()
        assert s11 is not None, "12月11日の有休が消えています！"
        assert s11.shift_type == models.ShiftType.PAID_LEAVE, f"12月11日が{s11.shift_type}で上書きされています！"

        # 通常の出勤日（例えば12月7日月曜日）は小林さんのシフト（月曜: 後半 SECOND など）が正常に自動生成されていること
        s7 = db.query(models.Shift).filter(
            models.Shift.user_id == user_id,
            models.Shift.date == date(2026, 12, 7)
        ).first()
        assert s7 is not None
        assert s7.shift_type == models.ShiftType.SECOND
    finally:
        db.close()

    # 8. カレンダーAPIおよび管理画面APIで有休・希休が正しく取得できること
    r_cal = client.get("/api/calendar/monthly?year=2026&month=12")
    assert r_cal.status_code == 200
    cal_data = r_cal.json()
    day8 = next(d for d in cal_data["days"] if d["day"] == 8)
    kob_shift_8 = next(s for s in day8["shifts"] if s["user_id"] == user_id)
    assert kob_shift_8["shift_type"] == "PAID_LEAVE"
    assert kob_shift_8["shift_label"] == "有休"

    day9 = next(d for d in cal_data["days"] if d["day"] == 9)
    kob_shift_9 = next(s for s in day9["shifts"] if s["user_id"] == user_id)
    assert kob_shift_9["shift_type"] == "HOPE_OFF"
    assert kob_shift_9["shift_label"] == "希休"

    # テスト後クリーンアップ
    db = SessionLocal()
    try:
        db.query(models.LeaveRequest).filter(models.LeaveRequest.date >= date(2026, 12, 1), models.LeaveRequest.date <= date(2026, 12, 31)).delete()
        db.query(models.Shift).filter(models.Shift.date >= date(2026, 12, 1), models.Shift.date <= date(2026, 12, 31)).delete()
        db.commit()
    finally:
        db.close()
