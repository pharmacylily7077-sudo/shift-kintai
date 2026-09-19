import os
import io
import csv
import pytest
from datetime import date, datetime, time, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_FILE = "test_kintai_robust.db"
if os.path.exists(TEST_DB_FILE):
    os.remove(TEST_DB_FILE)

from database import Base, get_db
import models
from main import app
from auth import hash_password, create_access_token

test_engine = create_engine(f"sqlite:///{TEST_DB_FILE}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    # テストユーザー投入（確定3名体制を模倣）
    admin_user = models.User(
        username="testadmin",
        password_hash=hash_password("adminpass"),
        full_name="三宅 智之（管理薬剤師）",
        role="admin",
        wage_type="MONTHLY",
        monthly_salary=450000,
        hourly_wage=2800,
        paid_leave_granted=15.0,
        paid_leave_carried=5.0,
        paid_leave_base_date=date(2026, 4, 1),
        work_days="0,1,2,3,4,5",
        default_start_time=time(9, 0),
        default_end_time=time(19, 0),
        default_break_minutes=60,
        color="#7c3aed",
        is_active=True
    )
    staff_user = models.User(
        username="teststaff",
        password_hash=hash_password("staffpass"),
        full_name="小林 彩乃（薬剤師）",
        role="staff",
        wage_type="HOURLY",
        hourly_wage=1500,
        monthly_salary=0,
        paid_leave_granted=10.0,
        paid_leave_carried=2.0,
        paid_leave_base_date=date(2026, 4, 1),
        work_days="0,1,2,4,5",
        default_start_time=time(9, 0),
        default_end_time=time(18, 0),
        default_break_minutes=60,
        color="#059669",
        is_active=True
    )
    staff_user2 = models.User(
        username="teststaff02",
        password_hash=hash_password("staffpass2"),
        full_name="寺内（調剤事務）",
        role="staff",
        wage_type="HOURLY",
        hourly_wage=1200,
        monthly_salary=0,
        paid_leave_granted=7.0,
        paid_leave_carried=1.0,
        paid_leave_base_date=date(2026, 4, 1),
        work_days="0,1,3,4,5",
        default_start_time=time(9, 0),
        default_end_time=time(18, 0),
        default_break_minutes=60,
        color="#0284c7",
        is_active=True
    )
    db.add_all([admin_user, staff_user, staff_user2])
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def staff_headers(client):
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def staff2_headers(client):
    res = client.post("/api/auth/login", json={"username": "teststaff02", "password": "staffpass2"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def admin_headers(client):
    res = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# ==============================================================================
# 1. 認証・権限・セキュリティ防御 (10テスト)
# ==============================================================================

def test_login_success_admin(client):
    res = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "admin"
    assert "access_token" in data

def test_login_success_staff(client):
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "staff"
    assert "access_token" in data

def test_login_failure_wrong_password(client):
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "wrongpassword"})
    assert res.status_code == 401
    assert "detail" in res.json()

def test_login_failure_nonexistent_user(client):
    res = client.post("/api/auth/login", json={"username": "nobody_user", "password": "anypassword"})
    assert res.status_code == 401

def test_unauthenticated_request_rejected(client):
    res = client.get("/api/me/dashboard")
    assert res.status_code == 401

def test_invalid_jwt_token_rejected(client):
    res = client.get("/api/me/dashboard", headers={"Authorization": "Bearer invalid.token.string"})
    assert res.status_code == 401

def test_expired_jwt_token_rejected(client):
    expired_token = create_access_token({"sub": "teststaff", "role": "staff"}, expires_delta=timedelta(seconds=-10))
    res = client.get("/api/me/dashboard", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401

def test_staff_cannot_access_admin_api(client, staff_headers):
    res = client.get("/api/admin/attendance/summary", headers=staff_headers)
    assert res.status_code == 403

def test_admin_cannot_delete_self(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    admin_id = [u["id"] for u in users_res.json() if u["username"] == "testadmin"][0]
    del_res = client.delete(f"/api/admin/users/{admin_id}", headers=admin_headers)
    assert del_res.status_code == 400

def test_staff_cannot_delete_other_user_shift_request(client, staff_headers, staff2_headers):
    create_res = client.post("/api/me/shift-requests", json={
        "date": "2026-11-20",
        "request_type": "OFF",
        "reason": "私用"
    }, headers=staff2_headers)
    assert create_res.status_code == 200
    req_id = create_res.json()["id"]

    del_res = client.delete(f"/api/me/shift-requests/{req_id}", headers=staff_headers)
    assert del_res.status_code == 404

# ==============================================================================
# 2. ステートマシン異常系・二重打刻・不正遷移完全ガード (15テスト)
# ==============================================================================

def test_clock_in_success(client, admin_headers):
    u_res = client.post("/api/admin/users", json={
        "username": "sm_staff1", "password": "pass", "full_name": "SMスタッフ1", "hourly_wage": 1500
    }, headers=admin_headers)
    assert u_res.status_code == 201

    login = client.post("/api/auth/login", json={"username": "sm_staff1", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    assert res.status_code == 200
    assert res.json()["status"] == "WORKING"

def test_clock_double_in_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff1", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    assert res.status_code == 400
    assert "すでに出勤" in res.json()["detail"]

def test_clock_break_start_without_in_blocked(client, admin_headers):
    client.post("/api/admin/users", json={
        "username": "sm_staff2", "password": "pass", "full_name": "SMスタッフ2"
    }, headers=admin_headers)
    login = client.post("/api/auth/login", json={"username": "sm_staff2", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=h)
    assert res.status_code == 400
    assert "勤務中ではない" in res.json()["detail"]

def test_clock_break_end_without_break_start_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff2", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "BREAK_END"}, headers=h)
    assert res.status_code == 400
    assert "休憩中ではない" in res.json()["detail"]

def test_clock_out_without_in_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff2", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "OUT"}, headers=h)
    assert res.status_code == 400
    assert "勤務中ではない" in res.json()["detail"]

def test_clock_full_cycle_normal(client, admin_headers):
    client.post("/api/admin/users", json={
        "username": "sm_staff3", "password": "pass", "full_name": "SMスタッフ3"
    }, headers=admin_headers)
    login = client.post("/api/auth/login", json={"username": "sm_staff3", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r1 = client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    assert r1.status_code == 200 and r1.json()["status"] == "WORKING"

    r2 = client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=h)
    assert r2.status_code == 200 and r2.json()["status"] == "ON_BREAK"

    r3 = client.post("/api/me/clock", json={"action": "BREAK_END"}, headers=h)
    assert r3.status_code == 200 and r3.json()["status"] == "WORKING"

    r4 = client.post("/api/me/clock", json={"action": "OUT"}, headers=h)
    assert r4.status_code == 200 and r4.json()["status"] == "LEFT"

def test_clock_out_after_out_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff3", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "OUT"}, headers=h)
    assert res.status_code == 400

def test_clock_in_after_out_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff3", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    assert res.status_code == 400

def test_clock_break_start_on_break_blocked(client, admin_headers):
    client.post("/api/admin/users", json={
        "username": "sm_staff4", "password": "pass", "full_name": "SMスタッフ4"
    }, headers=admin_headers)
    login = client.post("/api/auth/login", json={"username": "sm_staff4", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=h)

    res = client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=h)
    assert res.status_code == 400

def test_clock_break_end_when_working_blocked(client):
    login = client.post("/api/auth/login", json={"username": "sm_staff4", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    client.post("/api/me/clock", json={"action": "BREAK_END"}, headers=h)
    res = client.post("/api/me/clock", json={"action": "BREAK_END"}, headers=h)
    assert res.status_code == 400

def test_clock_out_while_on_break_auto_resolves_break(client, admin_headers):
    client.post("/api/admin/users", json={
        "username": "sm_staff5", "password": "pass", "full_name": "SMスタッフ5"
    }, headers=admin_headers)
    login = client.post("/api/auth/login", json={"username": "sm_staff5", "password": "pass"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    client.post("/api/me/clock", json={"action": "IN"}, headers=h)
    client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=h)
    res = client.post("/api/me/clock", json={"action": "OUT"}, headers=h)
    assert res.status_code == 200
    assert res.json()["status"] == "LEFT"

def test_clock_invalid_action_rejected(client, staff_headers):
    res = client.post("/api/me/clock", json={"action": "INVALID_ACTION"}, headers=staff_headers)
    assert res.status_code in [400, 422]

def test_admin_can_clock_in_out(client, admin_headers):
    res_in = client.post("/api/me/clock", json={"action": "IN"}, headers=admin_headers)
    assert res_in.status_code == 200
    assert res_in.json()["status"] == "WORKING"

    res_out = client.post("/api/me/clock", json={"action": "OUT"}, headers=admin_headers)
    assert res_out.status_code == 200
    assert res_out.json()["status"] == "LEFT"

def test_admin_clock_double_in_blocked(client, admin_headers):
    res = client.post("/api/me/clock", json={"action": "IN"}, headers=admin_headers)
    assert res.status_code == 400

def test_clock_work_minutes_calculation(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    u_id = users_res.json()[0]["id"]
    t_date = "2026-05-10"

    res = client.post("/api/admin/time-records", json={
        "user_id": u_id,
        "date": t_date,
        "clock_in": "09:00",
        "clock_out": "18:00",
        "total_break_minutes": 60
    }, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["total_work_minutes"] == 480

# ==============================================================================
# 3. バリデーション＆時間逆転・マイナス値完全防御 (10テスト)
# ==============================================================================

def test_correction_request_negative_break_blocked(client, staff_headers):
    res = client.post("/api/me/correction-request", json={
        "target_date": "2026-05-11",
        "requested_clock_in": "09:00",
        "requested_clock_out": "18:00",
        "requested_break_minutes": -30,
        "reason": "マイナス休憩"
    }, headers=staff_headers)
    assert res.status_code == 422

def test_correction_request_time_reversed_blocked(client, staff_headers):
    res = client.post("/api/me/correction-request", json={
        "target_date": "2026-05-11",
        "requested_clock_in": "18:00",
        "requested_clock_out": "09:00",
        "requested_break_minutes": 60,
        "reason": "時間逆転"
    }, headers=staff_headers)
    assert res.status_code == 422

def test_correction_request_break_exceeds_work_blocked(client, staff_headers):
    res = client.post("/api/me/correction-request", json={
        "target_date": "2026-05-11",
        "requested_clock_in": "09:00",
        "requested_clock_out": "10:00",
        "requested_break_minutes": 90,
        "reason": "過剰休憩"
    }, headers=staff_headers)
    assert res.status_code == 422

def test_admin_time_record_negative_break_blocked(client, admin_headers):
    res = client.post("/api/admin/time-records", json={
        "user_id": 1,
        "date": "2026-05-12",
        "clock_in": "09:00",
        "clock_out": "18:00",
        "total_break_minutes": -10
    }, headers=admin_headers)
    assert res.status_code == 422

def test_admin_time_record_time_reversed_blocked(client, admin_headers):
    res = client.post("/api/admin/time-records", json={
        "user_id": 1,
        "date": "2026-05-12",
        "clock_in": "19:00",
        "clock_out": "09:00",
        "total_break_minutes": 60
    }, headers=admin_headers)
    assert res.status_code == 422

def test_shift_create_negative_break_blocked(client, admin_headers):
    res = client.post("/api/admin/shifts", json={
        "user_id": 1,
        "date": "2026-05-13",
        "start_time": "09:00",
        "end_time": "18:00",
        "break_minutes": -20
    }, headers=admin_headers)
    assert res.status_code == 422

def test_shift_create_time_reversed_blocked(client, admin_headers):
    res = client.post("/api/admin/shifts", json={
        "user_id": 1,
        "date": "2026-05-13",
        "start_time": "18:00",
        "end_time": "09:00",
        "break_minutes": 60
    }, headers=admin_headers)
    assert res.status_code == 422

def test_shift_auto_generate_invalid_month_blocked(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 13,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 422

def test_shift_auto_generate_invalid_year_blocked(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 1899,
        "month": 5,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 422

def test_shift_request_invalid_type_blocked(client, staff_headers):
    res = client.post("/api/me/shift-requests", json={
        "date": "2026-06-01",
        "request_type": "ILLEGAL_TYPE",
        "reason": "テスト"
    }, headers=staff_headers)
    assert res.status_code == 422

# ==============================================================================
# 4. 日付境界値＆年跨ぎテスト (8テスト)
# ==============================================================================

def test_leap_year_february_29(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2024,
        "month": 2,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2024&month=2", headers=admin_headers).json()
    feb_29_shifts = [s for s in shifts if s["date"] == "2024-02-29"]
    assert len(feb_29_shifts) > 0

def test_common_year_february_28(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2025,
        "month": 2,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2025&month=2", headers=admin_headers).json()
    feb_29_shifts = [s for s in shifts if s["date"] == "2025-02-29"]
    assert len(feb_29_shifts) == 0

def test_short_month_30_days(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 4,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2026&month=4", headers=admin_headers).json()
    day_30 = [s for s in shifts if s["date"] == "2026-04-30"]
    day_31 = [s for s in shifts if s["date"] == "2026-04-31"]
    assert len(day_30) > 0
    assert len(day_31) == 0

def test_long_month_31_days(client, admin_headers):
    # 2026年7月31日は金曜日（全員の勤務日）
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 7,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2026&month=7", headers=admin_headers).json()
    day_31 = [s for s in shifts if s["date"] == "2026-07-31"]
    assert len(day_31) > 0

def test_year_boundary_december_to_january(client, admin_headers):
    res12 = client.post("/api/admin/shifts/auto-generate", json={"year": 2026, "month": 12, "overwrite": True}, headers=admin_headers)
    res01 = client.post("/api/admin/shifts/auto-generate", json={"year": 2027, "month": 1, "overwrite": True}, headers=admin_headers)
    assert res12.status_code == 200
    assert res01.status_code == 200

    s12 = client.get("/api/admin/shifts?year=2026&month=12", headers=admin_headers).json()
    s01 = client.get("/api/admin/shifts?year=2027&month=1", headers=admin_headers).json()
    assert any(s["date"] == "2026-12-31" for s in s12)
    assert any(s["date"] == "2027-01-01" for s in s01)

def test_month_range_edges_first_and_last_day(client, admin_headers):
    shifts = client.get("/api/admin/shifts?year=2026&month=4", headers=admin_headers).json()
    assert any(s["date"] == "2026-04-01" for s in shifts)
    assert any(s["date"] == "2026-04-30" for s in shifts)

def test_shifts_across_month_boundary(client, admin_headers):
    shifts = client.get("/api/admin/shifts?year=2026&month=4", headers=admin_headers).json()
    for s in shifts:
        assert s["date"].startswith("2026-04-")

def test_time_record_across_months(client, admin_headers):
    u_id = 1
    client.post("/api/admin/time-records", json={
        "user_id": u_id, "date": "2026-04-30", "clock_in": "09:00", "clock_out": "18:00", "total_break_minutes": 60
    }, headers=admin_headers)
    client.post("/api/admin/time-records", json={
        "user_id": u_id, "date": "2026-05-01", "clock_in": "09:00", "clock_out": "18:00", "total_break_minutes": 60
    }, headers=admin_headers)

    p_apr = client.get("/api/admin/payroll/monthly?year=2026&month=4", headers=admin_headers).json()
    p_may = client.get("/api/admin/payroll/monthly?year=2026&month=5", headers=admin_headers).json()

    user_apr = [item for item in p_apr["items"] if item["user_id"] == u_id][0]
    user_may = [item for item in p_may["items"] if item["user_id"] == u_id][0]
    assert user_apr["total_work_minutes"] >= 480
    assert user_may["total_work_minutes"] >= 480

# ==============================================================================
# 5. シフト管理＆一括自動生成ロジック (10テスト)
# ==============================================================================

def test_auto_generate_shifts_weekday_rules(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 6,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2026&month=6", headers=admin_headers).json()
    sat_shifts = [s for s in shifts if s["date"] == "2026-06-06"]
    assert len(sat_shifts) > 0

def test_auto_generate_skips_approved_off_request(client, staff_headers, admin_headers):
    target_d = "2026-07-07"
    req_res = client.post("/api/me/shift-requests", json={
        "date": target_d,
        "request_type": "OFF",
        "reason": "旅行"
    }, headers=staff_headers)
    assert req_res.status_code == 200
    req_id = req_res.json()["id"]

    rev = client.post(f"/api/admin/shift-requests/{req_id}/review", json={
        "status": "APPROVED",
        "admin_comment": "OK"
    }, headers=admin_headers)
    assert rev.status_code == 200

    gen_res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 7,
        "overwrite": True
    }, headers=admin_headers)
    assert gen_res.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2026&month=7", headers=admin_headers).json()
    user_shift = [s for s in shifts if s["date"] == target_d and s["user_name"] and "小林" in s["user_name"]]
    assert len(user_shift) == 0

def test_auto_generate_creates_paid_leave_shift(client, staff_headers, admin_headers):
    target_d = "2026-07-08"
    req_res = client.post("/api/me/shift-requests", json={
        "date": target_d,
        "request_type": "PAID_LEAVE",
        "reason": "通院"
    }, headers=staff_headers)
    assert req_res.status_code == 200
    req_id = req_res.json()["id"]

    client.post(f"/api/admin/shift-requests/{req_id}/review", json={
        "status": "APPROVED",
        "admin_comment": "有休承認"
    }, headers=admin_headers)

    client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 7,
        "overwrite": True
    }, headers=admin_headers)

    shifts = client.get("/api/admin/shifts?year=2026&month=7", headers=admin_headers).json()
    pl_shift = [s for s in shifts if s["date"] == target_d and s["user_name"] and "小林" in s["user_name"]]
    assert len(pl_shift) == 1
    assert pl_shift[0]["shift_type"] == "PAID_LEAVE"

def test_auto_generate_pending_request_not_skipped(client, staff_headers, admin_headers):
    d_mon = "2026-07-13"
    client.post("/api/me/shift-requests", json={
        "date": d_mon,
        "request_type": "OFF",
        "reason": "未承認希望"
    }, headers=staff_headers)

    client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 7,
        "overwrite": True
    }, headers=admin_headers)

    shifts = client.get("/api/admin/shifts?year=2026&month=7", headers=admin_headers).json()
    user_shift = [s for s in shifts if s["date"] == d_mon and s["user_name"] and "小林" in s["user_name"]]
    assert len(user_shift) == 1
    assert user_shift[0]["shift_type"] == "NORMAL"

def test_auto_generate_overwrite_behavior(client, admin_headers):
    u_id = 1
    client.post("/api/admin/shifts", json={
        "user_id": u_id,
        "date": "2026-08-10",
        "start_time": "10:00",
        "end_time": "15:00",
        "break_minutes": 30,
        "shift_type": "NORMAL",
        "note": "カスタムシフト"
    }, headers=admin_headers)

    client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 8,
        "overwrite": False
    }, headers=admin_headers)

    shifts = client.get("/api/admin/shifts?year=2026&month=8", headers=admin_headers).json()
    custom = [s for s in shifts if s["date"] == "2026-08-10" and s["user_id"] == u_id][0]
    assert custom["start_time"].startswith("10:00")

def test_manual_shift_creation_and_update(client, admin_headers):
    res = client.post("/api/admin/shifts", json={
        "user_id": 1,
        "date": "2026-09-01",
        "start_time": "09:00",
        "end_time": "17:00",
        "break_minutes": 60,
        "shift_type": "NORMAL",
        "note": "手動登録"
    }, headers=admin_headers)
    assert res.status_code == 200
    shift_id = res.json()["shift_id"]

    res_up = client.post("/api/admin/shifts", json={
        "user_id": 1,
        "date": "2026-09-01",
        "start_time": "09:30",
        "end_time": "18:00",
        "break_minutes": 60,
        "shift_type": "NORMAL",
        "note": "更新後"
    }, headers=admin_headers)
    assert res_up.status_code == 200

def test_manual_shift_delete(client, admin_headers):
    res = client.post("/api/admin/shifts", json={
        "user_id": 1,
        "date": "2026-09-02",
        "start_time": "09:00",
        "end_time": "17:00",
        "break_minutes": 60,
        "shift_type": "NORMAL"
    }, headers=admin_headers)
    shift_id = res.json()["shift_id"]

    del_res = client.delete(f"/api/admin/shifts/{shift_id}", headers=admin_headers)
    assert del_res.status_code == 200

def test_shift_duplicate_date_updates_existing(client, admin_headers):
    d = "2026-09-03"
    r1 = client.post("/api/admin/shifts", json={"user_id": 1, "date": d, "start_time": "09:00", "end_time": "17:00"}, headers=admin_headers)
    r2 = client.post("/api/admin/shifts", json={"user_id": 1, "date": d, "start_time": "10:00", "end_time": "18:00"}, headers=admin_headers)
    assert r1.status_code == 200 and r2.status_code == 200

    shifts = client.get("/api/admin/shifts?year=2026&month=9", headers=admin_headers).json()
    matching = [s for s in shifts if s["date"] == d and s["user_id"] == 1]
    assert len(matching) == 1
    assert matching[0]["start_time"].startswith("10:00")

def test_shift_requests_list_and_review_approve(client, staff_headers, admin_headers):
    r = client.post("/api/me/shift-requests", json={"date": "2026-10-01", "request_type": "OFF", "reason": "私用"}, headers=staff_headers)
    req_id = r.json()["id"]

    rev = client.post(f"/api/admin/shift-requests/{req_id}/review", json={"status": "APPROVED", "admin_comment": "承認済"}, headers=admin_headers)
    assert rev.status_code == 200
    assert rev.json()["status"] == "APPROVED"

def test_shift_requests_review_reject(client, staff_headers, admin_headers):
    r = client.post("/api/me/shift-requests", json={"date": "2026-10-02", "request_type": "OFF", "reason": "私用"}, headers=staff_headers)
    req_id = r.json()["id"]

    rev = client.post(f"/api/admin/shift-requests/{req_id}/review", json={"status": "REJECTED", "admin_comment": "人員不足のため"}, headers=admin_headers)
    assert rev.status_code == 200
    assert rev.json()["status"] == "REJECTED"

# ==============================================================================
# 6. 給与計算・有休手当・端数処理・扶養枠 (10テスト)
# ==============================================================================

def test_hourly_wage_calculation_exact_minutes(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    client.post("/api/admin/time-records", json={
        "user_id": staff_id,
        "date": "2026-11-01",
        "clock_in": "09:00",
        "clock_out": "17:30",
        "total_break_minutes": 60
    }, headers=admin_headers)

    p_res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers).json()
    item = [i for i in p_res["items"] if i["user_id"] == staff_id][0]
    assert item["work_salary"] == 11250

def test_paid_leave_allowance_addition(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    client.post("/api/admin/shifts", json={
        "user_id": staff_id,
        "date": "2026-11-02",
        "shift_type": "PAID_LEAVE"
    }, headers=admin_headers)

    p_res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers).json()
    item = [i for i in p_res["items"] if i["user_id"] == staff_id][0]
    assert item["paid_leave_allowance"] == 12000
    assert item["total_estimated_salary"] == item["work_salary"] + item["paid_leave_allowance"]

def test_monthly_salary_user_calculation(client, admin_headers):
    p_res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers).json()
    admin_item = [i for i in p_res["items"] if i["username"] == "testadmin"][0]
    assert admin_item["wage_type"] == "MONTHLY"
    assert admin_item["total_estimated_salary"] == 450000

def test_zero_work_minutes_no_division_by_zero(client, admin_headers):
    p_res = client.get("/api/admin/payroll/monthly?year=2029&month=1", headers=admin_headers)
    assert p_res.status_code == 200
    data = p_res.json()
    assert data["total_payout"] >= 450000

def test_rounding_precision_salary(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    client.post("/api/admin/time-records", json={
        "user_id": staff_id,
        "date": "2026-11-03",
        "clock_in": "09:00",
        "clock_out": "11:17",
        "total_break_minutes": 0
    }, headers=admin_headers)

    p_res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers).json()
    item = [i for i in p_res["items"] if i["user_id"] == staff_id][0]
    assert isinstance(item["work_salary"], int)

def test_monthly_payroll_summary_response_structure(client, admin_headers):
    res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "year" in data
    assert "month" in data
    assert "items" in data
    assert "total_payout" in data
    assert "total_work_hours" in data

def test_staff_dashboard_salary_projection(client, staff_headers):
    res = client.get("/api/me/dashboard", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert "confirmed_salary" in data
    assert "projected_month_end_salary" in data

def test_staff_dashboard_tax_103_limit_calculation(client, staff_headers):
    res = client.get("/api/me/dashboard", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tax_103_limit"] == 1030000
    assert "tax_103_remaining" in data
    assert "tax_103_hours_remaining" in data

def test_staff_dashboard_tax_130_limit_calculation(client, staff_headers):
    res = client.get("/api/me/dashboard", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tax_130_limit"] == 1300000
    assert "tax_130_remaining" in data
    assert "tax_130_hours_remaining" in data

def test_paid_leave_remaining_balance_calculation(client, staff_headers):
    res = client.get("/api/me/dashboard", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["paid_leave_total"] == 12.0
    assert "paid_leave_remaining" in data

# ==============================================================================
# 7. CSV出力＆特殊文字・エスケープ耐性 (6テスト)
# ==============================================================================

def test_export_csv_utf8_bom_presence(client, admin_headers):
    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    assert res.status_code == 200
    assert res.content.startswith(b'\xef\xbb\xbf')

def test_export_csv_headers_and_row_count(client, admin_headers):
    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    assert "氏名" in header
    assert "概算総支給額(円)" in header
    assert len(rows) >= 4

def test_export_csv_handles_commas_in_names(client, admin_headers):
    u_res = client.post("/api/admin/users", json={
        "username": "comma_user",
        "password": "pass",
        "full_name": "山田, 太郎（特命）"
    }, headers=admin_headers)
    assert u_res.status_code == 201

    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    names = [row[1] for row in reader]
    assert "山田, 太郎（特命）" in names

def test_export_csv_handles_quotes_in_data(client, admin_headers):
    u_res = client.post("/api/admin/users", json={
        "username": "quote_user",
        "password": "pass",
        "full_name": '田中 "リーダー" 次郎'
    }, headers=admin_headers)
    assert u_res.status_code == 201

    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    names = [row[1] for row in reader]
    assert '田中 "リーダー" 次郎' in names

def test_export_csv_handles_newlines_in_notes(client, admin_headers):
    users_res = client.get("/api/admin/users", headers=admin_headers)
    u_id = users_res.json()[0]["id"]
    client.post("/api/admin/time-records", json={
        "user_id": u_id,
        "date": "2026-11-25",
        "clock_in": "09:00",
        "clock_out": "18:00",
        "total_break_minutes": 60,
        "note": "1行目\n2行目の引き継ぎメモ"
    }, headers=admin_headers)

    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header_len = len(rows[0])
    for row in rows:
        assert len(row) == header_len

def test_export_csv_correct_totals(client, admin_headers):
    res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    text = res.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)[1:]
    for r in rows:
        work_sal = int(r[12])
        pl_allowance = int(r[13])
        total = int(r[14])
        if r[3] == "HOURLY":
            assert total == work_sal + pl_allowance
        elif r[3] == "MONTHLY":
            assert total == 450000

# ==============================================================================
# 8. フェーズ2＆3: 人員バランス判定・偏り警告機能 (5テスト)
# ==============================================================================

def test_shifts_balance_endpoint_structure(client, admin_headers):
    res = client.get("/api/admin/shifts/balance?year=2026&month=6", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["year"] == 2026
    assert data["month"] == 6
    assert "days" in data
    assert len(data["days"]) == 30
    assert "warning_days_count" in data
    day1 = data["days"][0]
    assert "date" in day1
    assert "weekday" in day1
    assert "total_staff" in day1
    assert "pharmacist_count" in day1
    assert "clerk_count" in day1
    assert "has_warning" in day1
    assert "warning_level" in day1
    assert "warning_messages" in day1

def test_shifts_balance_detects_empty_and_shortage(client, admin_headers):
    # 新しい月（2028年3月）でシフト未生成の場合、日曜日以外はdanger警告
    res = client.get("/api/admin/shifts/balance?year=2028&month=3", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    # 2028年3月は31日間、日曜日は4日あるので、営業日27日は未配置(total_staff==0)警告
    assert data["warning_days_count"] > 0
    non_sun_warnings = [d for d in data["days"] if d["weekday"] != 6 and d["has_warning"]]
    assert len(non_sun_warnings) > 0
    assert non_sun_warnings[0]["warning_level"] == "danger"

def test_shifts_balance_detects_no_pharmacist(client, admin_headers):
    # 2028年4月1日（土曜日）に調剤事務スタッフのみ登録した場合、薬剤師不在警告
    users_res = client.get("/api/admin/users", headers=admin_headers)
    clerk = [u for u in users_res.json() if "寺内" in u["full_name"]][0]

    client.post("/api/admin/shifts", json={
        "user_id": clerk["id"],
        "date": "2028-04-01",
        "start_time": "09:00",
        "end_time": "18:00",
        "shift_type": "NORMAL"
    }, headers=admin_headers)

    res = client.get("/api/admin/shifts/balance?year=2028&month=4", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    day1 = [d for d in data["days"] if d["date"] == "2028-04-01"][0]
    assert day1["pharmacist_count"] == 0
    assert day1["clerk_count"] == 1
    assert day1["has_warning"] is True
    assert day1["warning_level"] == "danger"
    assert any("薬剤師が不在" in msg for msg in day1["warning_messages"])

def test_shifts_balance_single_staff_warning(client, admin_headers):
    # 2028年5月1日（月曜日）に薬剤師1名のみ登録した場合、ワンオペwarning
    users_res = client.get("/api/admin/users", headers=admin_headers)
    pharma = [u for u in users_res.json() if "小林" in u["full_name"]][0]

    client.post("/api/admin/shifts", json={
        "user_id": pharma["id"],
        "date": "2028-05-01",
        "start_time": "09:00",
        "end_time": "18:00",
        "shift_type": "NORMAL"
    }, headers=admin_headers)

    res = client.get("/api/admin/shifts/balance?year=2028&month=5", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    day1 = [d for d in data["days"] if d["date"] == "2028-05-01"][0]
    assert day1["pharmacist_count"] == 1
    assert day1["total_staff"] == 1
    assert day1["has_warning"] is True
    assert day1["warning_level"] == "warning"
    assert any("ワンオペ" in msg for msg in day1["warning_messages"])

def test_auto_generate_returns_balance_warnings(client, admin_headers):
    res = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 6,
        "overwrite": True
    }, headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "warning_days_count" in data
    assert "balance_warnings" in data
    assert isinstance(data["balance_warnings"], list)

# ==============================================================================
# フェーズ4: 堅牢化・法改正対応・一括バックアップ テスト
# ==============================================================================
def test_shift_share_text_api(client, admin_headers):
    # シフト共有テキスト生成APIの検証
    res = client.get("/api/admin/shifts/share-text?year=2026&month=6", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["year"] == 2026
    assert data["month"] == 6
    assert "full_text" in data
    assert "by_staff" in data
    assert len(data["by_staff"]) >= 3
    assert "【ひまわり調剤薬局 2026年6月度" in data["full_text"]
    staff_names = [s["user_name"] for s in data["by_staff"]]
    assert any("三宅" in n for n in staff_names)
    assert any("小林" in n for n in staff_names)
    assert any("寺内" in n for n in staff_names)

def test_paid_leave_compliance_api(client, admin_headers):
    # 法定有給休暇 年5日取得義務コンプライアンス判定APIの検証
    res = client.get("/api/admin/compliance/paid-leave?year=2026", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["year"] == 2026
    assert "total_target_staff" in data
    assert "action_required_count" in data
    assert "staff" in data
    assert isinstance(data["staff"], list)
    # 三宅様（付与+繰越 20日）と小林様（12日）は10日以上の対象者
    assert data["total_target_staff"] >= 2
    for s in data["staff"]:
        assert s["status"] in ["ACHIEVED", "IN_PROGRESS", "ACTION_REQUIRED"]
        assert 0 <= s["legal_progress_percent"] <= 100

def test_backup_export_zip_api(client, admin_headers):
    import zipfile
    # 全データ一括バックアップ（ZIP/CSV）APIの検証
    res = client.get("/api/admin/backup/export", headers=admin_headers)
    assert res.status_code == 200
    assert "application/zip" in res.headers.get("content-type", "")
    assert "attachment; filename=shift_kintai_backup_" in res.headers.get("content-disposition", "")
    
    # ZIP解凍およびファイル構成チェック
    zip_bytes = io.BytesIO(res.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        file_list = zf.namelist()
        assert "users.csv" in file_list
        assert "shifts.csv" in file_list
        assert "time_records.csv" in file_list
        assert "shift_requests.csv" in file_list
        assert "correction_requests.csv" in file_list
        
        # users.csvの内容確認
        users_content = zf.read("users.csv").decode("utf-8-sig")
        assert "ユーザーID" in users_content
        assert "三宅 智之" in users_content
        assert "小林 彩乃" in users_content
