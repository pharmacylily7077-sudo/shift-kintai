import os
import pytest
from datetime import date, datetime, time, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_FILE = "test_kintai.db"
if os.path.exists(TEST_DB_FILE):
    os.remove(TEST_DB_FILE)

from database import Base, get_db
import models
from main import app
from auth import hash_password

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

    # テストユーザー投入
    admin_user = models.User(
        username="testadmin",
        password_hash=hash_password("adminpass"),
        full_name="テスト管理者",
        role="admin",
        wage_type="MONTHLY",
        monthly_salary=400000,
        hourly_wage=2500,
        paid_leave_granted=10.0,
        paid_leave_carried=2.0,
        is_active=True
    )
    staff_user = models.User(
        username="teststaff",
        password_hash=hash_password("staffpass"),
        full_name="テストスタッフ",
        role="staff",
        wage_type="HOURLY",
        hourly_wage=1500,
        paid_leave_granted=10.0,
        paid_leave_carried=2.0,
        is_active=True
    )
    db.add_all([admin_user, staff_user])
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)

@pytest.fixture
def client():
    return TestClient(app)

def test_login_success_and_failure(client):
    # 失敗系
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "wrongpassword"})
    assert res.status_code == 401

    # 成功系
    res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "staff"
    assert "access_token" in data
    assert "access_token" in res.cookies

def test_authorization_separation(client):
    login_res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # スタッフは /api/me/... にアクセス可能
    me_res = client.get("/api/me/dashboard", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["user"]["username"] == "teststaff"

    # スタッフが管理者APIにアクセスすると 403 Forbidden
    admin_res = client.get("/api/admin/attendance/summary", headers=headers)
    assert admin_res.status_code == 403

def test_clock_workflow(client):
    login_res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 出勤打刻
    clock_in_res = client.post("/api/me/clock", json={"action": "IN"}, headers=headers)
    assert clock_in_res.status_code == 200
    assert clock_in_res.json()["status"] == "WORKING"

    # 2. 二重出勤はエラー
    dup_res = client.post("/api/me/clock", json={"action": "IN"}, headers=headers)
    assert dup_res.status_code == 400

    # 3. 休憩入
    break_res = client.post("/api/me/clock", json={"action": "BREAK_START"}, headers=headers)
    assert break_res.status_code == 200
    assert break_res.json()["status"] == "ON_BREAK"

    # 4. 休憩戻
    break_end_res = client.post("/api/me/clock", json={"action": "BREAK_END"}, headers=headers)
    assert break_end_res.status_code == 200
    assert break_end_res.json()["status"] == "WORKING"

    # 5. 退勤
    out_res = client.post("/api/me/clock", json={"action": "OUT"}, headers=headers)
    assert out_res.status_code == 200
    assert out_res.json()["status"] == "LEFT"

def test_settings_and_correction_request(client):
    login_res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 設定変更 (時給を1600円に更新)
    set_res = client.put("/api/me/settings", json={"hourly_wage": 1600}, headers=headers)
    assert set_res.status_code == 200
    assert set_res.json()["hourly_wage"] == 1600

    # 打刻修正申請
    target_date = date.today().isoformat()
    req_res = client.post("/api/me/correction-request", json={
        "target_date": target_date,
        "requested_clock_in": "09:00",
        "requested_clock_out": "18:00",
        "requested_break_minutes": 60,
        "reason": "打刻忘れのため修正依頼"
    }, headers=headers)
    assert req_res.status_code == 200
    assert req_res.json()["status"] == "PENDING"
    req_id = req_res.json()["id"]

    # 管理者でログインして承認
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    review_res = client.post(f"/api/admin/correction-requests/{req_id}/review", json={
        "status": "APPROVED",
        "admin_comment": "確認の上承認しました"
    }, headers=admin_headers)
    assert review_res.status_code == 200

def test_admin_shift_and_csv_export(client):
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # スタッフ一覧から teststaff の ID を取得
    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    # シフト作成
    today_str = date.today().isoformat()
    shift_res = client.post("/api/admin/shifts", json={
        "user_id": staff_id,
        "date": today_str,
        "start_time": "09:00",
        "end_time": "18:00",
        "break_minutes": 60,
        "shift_type": "NORMAL",
        "note": "テストシフト"
    }, headers=admin_headers)
    assert shift_res.status_code == 200

    # CSVエクスポート
    today = date.today()
    csv_res = client.get(f"/api/admin/export-csv?year={today.year}&month={today.month}", headers=admin_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    content = csv_res.content
    assert content.startswith(b'\xef\xbb\xbf')
    assert "テストスタッフ" in content.decode("utf-8-sig")

def test_html_pages_and_redirects(client):
    # 未ログインで / にアクセスすると /login へリダイレクト
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"

    # /login ページは 200 OK でHTMLが返る
    res = client.get("/login")
    assert res.status_code == 200
    assert "薬局" in res.text

    # スタッフログイン時の / へのアクセス
    login_res = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    cookie = login_res.cookies.get("access_token")
    client.cookies.set("access_token", cookie)

    res = client.get("/")
    assert res.status_code == 200
    assert "マイページ" in res.text
    assert "テストスタッフ" in res.text

    # 管理者ログイン時の /admin へのアクセス
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_cookie = admin_login.cookies.get("access_token")
    client.cookies.set("access_token", admin_cookie)

    res = client.get("/admin")
    assert res.status_code == 200
    assert "管理者ポータル" in res.text

def test_user_condition_update(client):
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    # 雇用条件を更新
    cond_res = client.put(f"/api/admin/users/{staff_id}/condition", json={
        "work_days": "0,2,4",
        "default_start_time": "09:00",
        "default_end_time": "17:00",
        "default_break_minutes": 60,
        "color": "#0d9488",
        "hourly_wage": 1650
    }, headers=admin_headers)
    assert cond_res.status_code == 200
    data = cond_res.json()
    assert data["work_days"] == "0,2,4"
    assert data["default_start_time"] == "09:00:00"
    assert data["default_end_time"] == "17:00:00"
    assert data["color"] == "#0d9488"
    assert data["hourly_wage"] == 1650

def test_shift_requests_workflow(client):
    # スタッフログイン
    staff_login = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # 1. 希望休（OFF）を提出
    req1_date = (date.today() + timedelta(days=5)).isoformat()
    res1 = client.post("/api/me/shift-requests", json={
        "date": req1_date,
        "request_type": "OFF",
        "reason": "私用のため"
    }, headers=staff_headers)
    assert res1.status_code == 200
    req1_id = res1.json()["id"]
    assert res1.json()["status"] == "PENDING"

    # 2. 有休希望（PAID_LEAVE）を提出
    req2_date = (date.today() + timedelta(days=6)).isoformat()
    res2 = client.post("/api/me/shift-requests", json={
        "date": req2_date,
        "request_type": "PAID_LEAVE",
        "reason": "年次有給休暇取得"
    }, headers=staff_headers)
    assert res2.status_code == 200
    req2_id = res2.json()["id"]

    # 3. 自分の申請一覧取得
    my_reqs = client.get("/api/me/shift-requests", headers=staff_headers)
    assert my_reqs.status_code == 200
    ids = [r["id"] for r in my_reqs.json()]
    assert req1_id in ids
    assert req2_id in ids

    # 4. 希望休（req1）を取り消し
    del_res = client.delete(f"/api/me/shift-requests/{req1_id}", headers=staff_headers)
    assert del_res.status_code == 200

    # 5. 管理者ログインして審査
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_reqs = client.get("/api/admin/shift-requests", headers=admin_headers)
    assert admin_reqs.status_code == 200
    pending_ids = [r["id"] for r in admin_reqs.json() if r["status"] == "PENDING"]
    assert req2_id in pending_ids

    # 承認
    review_res = client.post(f"/api/admin/shift-requests/{req2_id}/review", json={
        "status": "APPROVED",
        "admin_comment": "承認しました"
    }, headers=admin_headers)
    assert review_res.status_code == 200

    # 有休シフトが自動生成されたことを確認
    shifts_res = client.get(f"/api/admin/shifts?year={date.today().year}&month={date.today().month}", headers=admin_headers)
    assert shifts_res.status_code == 200
    paid_leave_shifts = [s for s in shifts_res.json() if s["date"] == req2_date and s["shift_type"] == "PAID_LEAVE"]
    assert len(paid_leave_shifts) == 1
    assert paid_leave_shifts[0]["user_color"] == "#0d9488"

def test_auto_generate_shifts(client):
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    staff_login = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # 来月のシフトを自動生成テスト
    today = date.today()
    target_year = today.year if today.month < 12 else today.year + 1
    target_month = today.month + 1 if today.month < 12 else 1

    # スタッフの雇用条件: 月・水 (0, 2)
    users_res = client.get("/api/admin/users", headers=admin_headers)
    staff_id = [u["id"] for u in users_res.json() if u["username"] == "teststaff"][0]

    client.put(f"/api/admin/users/{staff_id}/condition", json={
        "work_days": "0,2",
        "default_start_time": "09:00",
        "default_end_time": "18:00",
        "default_break_minutes": 60,
        "color": "#059669"
    }, headers=admin_headers)

    # 対象月の第1水曜日を検索
    first_wednesday = None
    first_monday = None
    for d_num in range(1, 15):
        d = date(target_year, target_month, d_num)
        if d.weekday() == 2 and not first_wednesday:
            first_wednesday = d
        if d.weekday() == 0 and not first_monday:
            first_monday = d

    # 第1水曜日に希望休（OFF）を提出・承認
    req_res = client.post("/api/me/shift-requests", json={
        "date": first_wednesday.isoformat(),
        "request_type": "OFF",
        "reason": "旅行のため"
    }, headers=staff_headers)
    req_id = req_res.json()["id"]

    client.post(f"/api/admin/shift-requests/{req_id}/review", json={
        "status": "APPROVED"
    }, headers=admin_headers)

    # 一括自動生成を実行
    gen_res = client.post("/api/admin/shifts/auto-generate", json={
        "year": target_year,
        "month": target_month,
        "overwrite": True
    }, headers=admin_headers)
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["generated"] > 0
    assert gen_data["skipped_requests"] >= 1

    # 生成されたシフトを検証
    shifts_res = client.get(f"/api/admin/shifts?year={target_year}&month={target_month}", headers=admin_headers)
    shifts = shifts_res.json()

    # 月曜日には通常シフトが存在すること
    monday_shifts = [s for s in shifts if s["date"] == first_monday.isoformat() and s["user_id"] == staff_id]
    assert len(monday_shifts) == 1
    assert monday_shifts[0]["shift_type"] == "NORMAL"

    # 希望休の水曜日にはシフトが存在しない（スキップされた）こと
    wed_shifts = [s for s in shifts if s["date"] == first_wednesday.isoformat() and s["user_id"] == staff_id]
    assert len(wed_shifts) == 0

    # 雇用条件変更（月曜を除外し水曜のみ）後の上書き再生成で、非勤務日となった月曜シフトが削除されることを検証
    client.put(f"/api/admin/users/{staff_id}/condition", json={
        "work_days": "2",
    }, headers=admin_headers)

    gen_res2 = client.post("/api/admin/shifts/auto-generate", json={
        "year": target_year,
        "month": target_month,
        "overwrite": True
    }, headers=admin_headers)
    assert gen_res2.status_code == 200

    shifts_res2 = client.get(f"/api/admin/shifts?year={target_year}&month={target_month}", headers=admin_headers)
    monday_shifts2 = [s for s in shifts_res2.json() if s["date"] == first_monday.isoformat() and s["user_id"] == staff_id]
    assert len(monday_shifts2) == 0

def test_pwa_and_print_assets(client):
    # manifest.json の配信確認
    m_res = client.get("/manifest.json")
    assert m_res.status_code == 200
    m_json = m_res.json()
    assert m_json["short_name"] == "薬局勤怠"
    assert m_json["display"] == "standalone"

    # service-worker.js の配信確認
    sw_res = client.get("/service-worker.js")
    assert sw_res.status_code == 200
    assert "CACHE_NAME" in sw_res.text

    # アイコンファイルの配信確認
    icon_res = client.get("/static/icons/icon-192.png")
    assert icon_res.status_code == 200
    assert icon_res.headers["content-type"] == "image/png"

