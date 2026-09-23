import pytest
from datetime import date, time
from fastapi.testclient import TestClient
from main import app
from seed import seed_data
from database import SessionLocal
import models

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_data()

@pytest.fixture
def auth_staff():
    client = TestClient(app)
    # 家田さんでログイン
    res = client.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "ieda",
        "password": "ieda1234"
    })
    assert res.status_code == 200
    return client

def test_vacation_self_management_and_apply(auth_staff):
    """有休の自己管理（残日数設定）および申請機能の検証"""
    # 1. 有休残日数を自分で 14.5 日に設定
    res_set = auth_staff.put("/api/me/paid-leave", json={"paid_leave_remaining": 14.5})
    assert res_set.status_code == 200
    assert res_set.json()["paid_leave_remaining"] == 14.5

    # 2. 有給休暇の申請送信
    target_date = "2026-09-28"
    res_apply = auth_staff.post("/api/me/leave-requests", json={
        "date": target_date,
        "request_type": "ADVANCE",
        "leave_type": "PAID_LEAVE",
        "reason": "私用のため有休希望"
    })
    assert res_apply.status_code == 200
    assert res_apply.json()["success"] is True

    # 3. 申請履歴取得
    res_list = auth_staff.get("/api/me/leave-requests")
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(it["date"] == target_date and it["leave_type"] == "PAID_LEAVE" for it in items)

def test_clock_and_payroll_evidence_shield(auth_staff):
    """出退勤打刻・残業算出・言いがかり封じのガラス張り計算検証"""
    # 1. 出勤打刻
    r_in = auth_staff.post("/api/me/clock", json={"action": "IN"})
    assert r_in.status_code == 200
    assert r_in.json()["status"] == "WORKING"

    # 2. 時給を 2,000 円に設定
    r_wage = auth_staff.put("/api/me/wage", json={"hourly_wage": 2000})
    assert r_wage.status_code == 200
    assert r_wage.json()["hourly_wage"] == 2000

    # 3. テスト用の実績レコード（9時間実働 = 8時間通常 + 1時間残業）を注入
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.username == "ieda").first()
    test_record = models.TimeRecord(
        user_id=user.id,
        date=date(2026, 9, 10),
        clock_in=time(9, 0),
        clock_out=time(19, 0),
        break_start=time(13, 0),
        break_end=time(14, 0),
        status=models.ClockStatus.DONE
    )
    db.add(test_record)
    db.commit()
    db.close()

    # 4. ダッシュボードで給与・残業速報と内訳を確認
    res_dash = auth_staff.get("/api/me/dashboard")
    assert res_dash.status_code == 200
    sim = res_dash.json()["salary_simulator"]

    assert sim["hourly_wage"] == 2000
    # 9時間（540分）実働 -> 通常480分(8h) + 残業60分(1h)
    assert sim["overtime_minutes"] >= 60
    assert sim["overtime_hours"] >= 1.0
    # 8h * 2000 + 1h * 2000 * 1.25 = 16000 + 2500 = 18500
    assert sim["estimated_salary"] >= 18500
    # 詳細内訳リストの検証
    assert len(sim["daily_records"]) > 0
    rec = [r for r in sim["daily_records"] if r["date"] == "2026-09-10"][0]
    assert rec["clock_in"] == "09:00"
    assert rec["clock_out"] == "19:00"
    assert rec["work_minutes"] == 540
    assert rec["overtime_minutes"] == 60
