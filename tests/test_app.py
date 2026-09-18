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

def test_weekly_schedule_and_shift_generation(client):
    import json
    # 管理者ログイン
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # 1. 曜日別スケジュールを持つ新規スタッフを登録
    weekly_data = {
        "0": {"work": True, "start": "09:00", "end": "19:00", "break": 60},  # 月: 9:00-19:00 (休60)
        "1": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "2": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "3": {"work": True, "start": "09:00", "end": "13:00", "break": 0},   # 木: 9:00-13:00 (休0)
        "4": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "5": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "6": {"work": False, "start": "09:00", "end": "18:00", "break": 60}  # 日: 休み
    }
    weekly_json = json.dumps(weekly_data)

    create_res = client.post("/api/admin/users", json={
        "username": "weekdaystaff",
        "password": "password123",
        "full_name": "曜日別スタッフ",
        "role": "staff",
        "wage_type": "HOURLY",
        "hourly_wage": 1600,
        "weekly_schedule": weekly_json
    }, headers=admin_headers)
    assert create_res.status_code == 201
    created_user = create_res.json()
    user_id = created_user["id"]
    assert created_user["weekly_schedule"] == weekly_json

    # 2. 雇用条件更新で weekly_schedule が正しく更新できることの検証
    updated_weekly = {
        "0": {"work": True, "start": "09:00", "end": "18:00", "break": 60},
        "1": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "2": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "3": {"work": True, "start": "09:00", "end": "12:30", "break": 0},
        "4": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "5": {"work": False, "start": "09:00", "end": "18:00", "break": 60},
        "6": {"work": False, "start": "09:00", "end": "18:00", "break": 60}
    }
    update_res = client.put(f"/api/admin/users/{user_id}/condition", json={
        "weekly_schedule": json.dumps(updated_weekly)
    }, headers=admin_headers)
    assert update_res.status_code == 200
    assert update_res.json()["weekly_schedule"] == json.dumps(updated_weekly)

    # 3. シフト自動生成を実行して、曜日ごとの時間設定が正しく反映されることの検証
    target_year = 2026
    target_month = 11

    gen_res = client.post("/api/admin/shifts/auto-generate", json={
        "year": target_year,
        "month": target_month,
        "overwrite": True
    }, headers=admin_headers)
    assert gen_res.status_code == 200

    shifts_res = client.get(f"/api/admin/shifts?year={target_year}&month={target_month}", headers=admin_headers)
    shifts = shifts_res.json()

    user_shifts = [s for s in shifts if s["user_id"] == user_id]
    assert len(user_shifts) > 0

    # 生成された月曜日のシフトと木曜日のシフトをチェック
    for s in user_shifts:
        d = datetime.strptime(s["date"], "%Y-%m-%d").date()
        if d.weekday() == 0:  # 月曜日
            assert s["start_time"] == "09:00"
            assert s["end_time"] == "18:00"
            assert s["break_minutes"] == 60
        elif d.weekday() == 3:  # 木曜日
            assert s["start_time"] == "09:00"
            assert s["end_time"] == "12:30"
            assert s["break_minutes"] == 0
        else:
            # 月曜・木曜以外は enabled ではないので生成されない
            pytest.fail(f"Unexpected shift on weekday {d.weekday()} for date {s['date']}")

def test_shift_manual_crud_and_reflection(client):
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = admin_login.json()["user_id"] if "user_id" in admin_login.json() else 1

    staff_login = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}
    staff_me = client.get("/api/me/dashboard", headers=staff_headers).json()["user"]
    staff_id = staff_me["id"]

    # 1. 管理者自身へのシフト手動登録（9:00 - 19:00）
    res = client.post("/api/admin/shifts", json={
        "user_id": admin_id,
        "date": "2026-12-01",
        "shift_type": "NORMAL",
        "start_time": "09:00",
        "end_time": "19:00",
        "break_minutes": 60,
        "note": "管理者手動登録"
    }, headers=admin_headers)
    assert res.status_code == 200

    # 2. スタッフへのシフト手動登録（9:00 - 18:00）
    res2 = client.post("/api/admin/shifts", json={
        "user_id": staff_id,
        "date": "2026-12-01",
        "shift_type": "NORMAL",
        "start_time": "09:00",
        "end_time": "18:00",
        "break_minutes": 60,
        "note": "スタッフ手動登録"
    }, headers=admin_headers)
    assert res2.status_code == 200
    shift_id = res2.json()["shift_id"]

    # 3. 管理者シフト一覧での反映確認
    list_res = client.get("/api/admin/shifts?year=2026&month=12", headers=admin_headers)
    assert list_res.status_code == 200
    shifts = list_res.json()
    dec1_shifts = [s for s in shifts if s["date"] == "2026-12-01"]
    assert len(dec1_shifts) == 2
    admin_s = next(s for s in dec1_shifts if s["user_id"] == admin_id)
    assert admin_s["start_time"] == "09:00"
    assert admin_s["end_time"] == "19:00"

    # 4. スタッフ画面 (/api/me/shifts) での自分のシフト反映確認
    my_shifts_res = client.get("/api/me/shifts?year=2026&month=12", headers=staff_headers)
    assert my_shifts_res.status_code == 200
    my_shifts = my_shifts_res.json()
    day1_info = next(item for item in my_shifts if item["date"] == "2026-12-01")
    assert day1_info["shift"] is not None
    assert day1_info["shift"]["start_time"] == "09:00"
    assert day1_info["shift"]["end_time"] == "18:00"

    # 5. シフト削除の確認
    del_res = client.delete(f"/api/admin/shifts/{shift_id}", headers=admin_headers)
    assert del_res.status_code == 200

    # 削除後の確認
    my_shifts_res2 = client.get("/api/me/shifts?year=2026&month=12", headers=staff_headers)
    day1_info_after = next(item for item in my_shifts_res2.json() if item["date"] == "2026-12-01")
    assert day1_info_after["shift"] is None

def test_admin_direct_time_record_and_monthly_payroll(client):
    admin_login = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpass"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    staff_login = client.post("/api/auth/login", json={"username": "teststaff", "password": "staffpass"})
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}
    staff_me = client.get("/api/me/dashboard", headers=staff_headers).json()["user"]
    staff_id = staff_me["id"]

    # 1. 管理者がスタッフの勤怠実績を手動直接入力（9:00〜18:00、休憩60分 = 実働8時間480分）
    rec_res = client.post("/api/admin/time-records", json={
        "user_id": staff_id,
        "date": "2026-11-10",
        "clock_in": "09:00",
        "clock_out": "18:00",
        "total_break_minutes": 60,
        "note": "管理者手動登録テスト"
    }, headers=admin_headers)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["total_work_minutes"] == 480
    assert rec_data["is_corrected"] is True
    assert rec_data["status"] == "LEFT"

    # 2. スタッフに有休シフト（PAID_LEAVE）を登録
    pl_res = client.post("/api/admin/shifts", json={
        "user_id": staff_id,
        "date": "2026-11-11",
        "shift_type": "PAID_LEAVE",
        "note": "有休テスト"
    }, headers=admin_headers)
    assert pl_res.status_code == 200

    # 3. 月次給与集計API (GET /api/admin/payroll/monthly) の検証
    payroll_res = client.get("/api/admin/payroll/monthly?year=2026&month=11", headers=admin_headers)
    assert payroll_res.status_code == 200
    p_data = payroll_res.json()
    assert p_data["year"] == 2026
    assert p_data["month"] == 11

    # スタッフの集計行を確認
    staff_p = next(item for item in p_data["items"] if item["user_id"] == staff_id)
    assert staff_p["work_days_count"] == 1
    assert staff_p["total_work_minutes"] == 480
    assert staff_p["total_work_hours_str"] == "8時間00分"
    assert staff_p["paid_leave_days_count"] == 1.0

    # 時給に基づく計算確認 (8時間実労働 + 8時間有休手当)
    wage = staff_p["hourly_wage"]
    expected_work_sal = 8 * wage
    expected_pl_allowance = 8 * wage
    expected_total = expected_work_sal + expected_pl_allowance

    assert staff_p["work_salary"] == expected_work_sal
    assert staff_p["paid_leave_allowance"] == expected_pl_allowance
    assert staff_p["total_estimated_salary"] == expected_total

    # 4. 給与CSVダウンロード (GET /api/admin/export-csv) の検証
    csv_res = client.get("/api/admin/export-csv?year=2026&month=11", headers=admin_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    csv_text = csv_res.content.decode("utf-8")
    assert "有休手当(円)" in csv_text
    assert "概算総支給額(円)" in csv_text
    assert str(expected_total) in csv_text

    # 5. スタッフマイページ (/api/me/dashboard) の取得検証
    dash_res = client.get("/api/me/dashboard", headers=staff_headers)
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert dash["confirmed_salary"] >= 0
    assert dash["projected_month_end_salary"] >= 0





