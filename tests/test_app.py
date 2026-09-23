import pytest
from datetime import date
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
import models

@pytest.fixture
def client():
    return TestClient(app)

def test_login_triple_lock(client):
    """三重ロックの動作検証"""
    # 1. 薬剤師スタッフ取得
    r1 = client.get("/api/auth/staff-list?position=PHARMACIST")
    assert r1.status_code == 200
    names = [x["full_name"] for x in r1.json()]
    assert any("三宅" in n for n in names) and any("家田" in n for n in names)

    # 2. 調剤補助スタッフ取得
    r2 = client.get("/api/auth/staff-list?position=ASSISTANT")
    assert r2.status_code == 200
    names = [x["full_name"] for x in r2.json()]
    assert any("小林" in n for n in names) and any("本間" in n for n in names)

    # 3. ログイン認証（小林さん）
    r3 = client.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi1234"
    })
    assert r3.status_code == 200
    assert "小林" in r3.json()["full_name"]

def test_calendar_no_salary_leak(client):
    """公開カレンダーに給与情報が一切漏洩していないこと"""
    r = client.get("/api/calendar/monthly?year=2026&month=9")
    assert r.status_code == 200
    raw = r.text.lower()
    assert "wage" not in raw
    assert "salary" not in raw
    assert "hourly" not in raw
    assert "paid_leave" not in raw

def test_sunday_and_holidays_off_and_rules(client):
    """日祝休日および個別定休日（火曜・木曜）の自動生成検証"""
    # 管理者ログイン
    r_admin = client.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "miyake",
        "password": "admin123"
    })
    cookies = r_admin.cookies

    # 2026年9月の一括生成（9/21=敬老の日, 9/22=国民の休日, 9/23=秋分の日）
    r_gen = client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 9,
        "overwrite": True
    }, cookies=cookies)
    assert r_gen.status_code == 200

    db = SessionLocal()
    # 日祝休日はシフト0件
    for hol in [date(2026, 9, 20), date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]:
        assert db.query(models.Shift).filter(models.Shift.date == hol).count() == 0

    # 小林さんは木曜日休み（9/3, 9/10, 9/17, 9/24）
    u_koba = db.query(models.User).filter(models.User.username == "kobayashi").first()
    for thur in [date(2026, 9, 3), date(2026, 9, 10), date(2026, 9, 17), date(2026, 9, 24)]:
        assert db.query(models.Shift).filter(models.Shift.user_id == u_koba.id, models.Shift.date == thur).first() is None

    # 家田さんは火曜日休み（9/1, 9/8, 9/15, 9/29）
    u_ieda = db.query(models.User).filter(models.User.username == "ieda").first()
    for tue in [date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15), date(2026, 9, 29)]:
        assert db.query(models.Shift).filter(models.Shift.user_id == u_ieda.id, models.Shift.date == tue).first() is None

    # 新ルール1: 土曜日は出勤者全員「午前診 (AM)」
    for sat in [date(2026, 9, 5), date(2026, 9, 12), date(2026, 9, 19), date(2026, 9, 26)]:
        sat_shifts = db.query(models.Shift).filter(models.Shift.date == sat).all()
        assert len(sat_shifts) > 0
        for s in sat_shifts:
            assert s.shift_type == models.ShiftType.AM

    # 新ルール2: 本間さんは木曜日「午前診 (AM)」
    u_honma = db.query(models.User).filter(models.User.username == "honma").first()
    for thur in [date(2026, 9, 3), date(2026, 9, 10), date(2026, 9, 17), date(2026, 9, 24)]:
        h_shift = db.query(models.Shift).filter(models.Shift.user_id == u_honma.id, models.Shift.date == thur).first()
        assert h_shift is not None
        assert h_shift.shift_type == models.ShiftType.AM

    # 新ルール3: 小林さんは火曜日「午前診 (AM)」
    for tue in [date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15), date(2026, 9, 29)]:
        k_shift = db.query(models.Shift).filter(models.Shift.user_id == u_koba.id, models.Shift.date == tue).first()
        assert k_shift is not None
        assert k_shift.shift_type == models.ShiftType.AM

    db.close()

def test_myroom_priorities(client):
    """マイルームの自己管理機能（給与・有休・体調・家計簿）検証"""
    res = client.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi1234"
    })
    cookies = res.cookies

    # 優先度1: 時給設定
    r1 = client.put("/api/me/wage", json={"hourly_wage": 1200}, cookies=cookies)
    assert r1.status_code == 200

    # 優先度2: 有休設定
    r2 = client.put("/api/me/paid-leave", json={"paid_leave_remaining": 10.0}, cookies=cookies)
    assert r2.status_code == 200

    # 優先度3: 体調記録
    r3 = client.post("/api/me/health", json={"date": "2026-09-20", "health_status": "GOOD", "note": "快調"}, cookies=cookies)
    assert r3.status_code == 200

    # 優先度4: 家計簿
    r4 = client.post("/api/me/budget", json={"date": "2026-09-20", "title": "お昼ご飯", "amount": 800, "is_income": False}, cookies=cookies)
    assert r4.status_code == 200

    # ダッシュボード取得確認
    r_dash = client.get("/api/me/dashboard", cookies=cookies)
    assert r_dash.status_code == 200
    d = r_dash.json()
    assert d["salary_simulator"]["hourly_wage"] == 1200
    assert d["paid_leave"]["remaining"] == 10.0
