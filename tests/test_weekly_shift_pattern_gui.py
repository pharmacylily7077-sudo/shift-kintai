"""
tests/test_weekly_shift_pattern_gui.py
管理画面からの曜日別シフト自由設定（Weekly Shift Pattern）および自動生成連動の検証
"""
import pytest
import json
from datetime import date
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
import models

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def admin_client(client):
    r = client.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "miyake",
        "password": "admin123"
    })
    assert r.status_code == 200
    return client

def test_weekly_shift_pattern_gui_flow(admin_client):
    """
    管理画面からのスタッフ曜日別シフト設定（Weekly Shift Pattern）の取得・更新・自動生成連動の検証
    """
    db = SessionLocal()
    try:
        kobayashi = db.query(models.User).filter(models.User.username == "kobayashi").first()
        assert kobayashi is not None
        k_id = kobayashi.id
    finally:
        db.close()

    # 1. スタッフ条件一覧の取得検証
    res_get = admin_client.get("/api/admin/staff/conditions")
    assert res_get.status_code == 200
    staff_list = res_get.json()["staff"]
    k_staff = next(s for s in staff_list if s["id"] == k_id)
    assert k_staff["weekly_shift_pattern"] is not None
    wp = json.loads(k_staff["weekly_shift_pattern"])
    assert wp["0"] == "SECOND" # 月: 後半
    assert wp["1"] == "FIRST"  # 火: 前半
    assert wp["3"] == "OFF"    # 木: 休み
    assert wp["5"] == "AM"     # 土: 午前診

    # 2. 小林彩乃さんの火曜日を「午前診 (AM)」に変更して保存
    wp["1"] = "AM"
    res_put = admin_client.put(f"/api/admin/staff/{k_id}/condition", json={
        "weekly_shift_pattern": json.dumps(wp)
    })
    assert res_put.status_code == 200
    put_data = res_put.json()
    assert put_data["success"] is True

    # 3. 2026年11月のシフトを一括自動生成
    res_gen = admin_client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 11,
        "overwrite": True
    })
    assert res_gen.status_code == 200

    # 4. 2026年11月の火曜日（11/3は文化の日祝日なので休局、11/10, 11/17, 11/24）のシフトを検証
    db = SessionLocal()
    try:
        for tue in [date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 24)]:
            s = db.query(models.Shift).filter(models.Shift.user_id == k_id, models.Shift.date == tue).first()
            assert s is not None
            # 画面から変更した通り「午前診 (AM)」になっている！
            assert s.shift_type == models.ShiftType.AM
    finally:
        db.close()

    # 5. 火曜日を本来の「前半 (FIRST)」に戻して再保存・再生成
    wp["1"] = "FIRST"
    admin_client.put(f"/api/admin/staff/{k_id}/condition", json={
        "weekly_shift_pattern": json.dumps(wp)
    })
    admin_client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 11,
        "overwrite": True
    })

    db = SessionLocal()
    try:
        for tue in [date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 24)]:
            s = db.query(models.Shift).filter(models.Shift.user_id == k_id, models.Shift.date == tue).first()
            assert s is not None
            # 元通り「前半 (FIRST)」に戻った！
            assert s.shift_type == models.ShiftType.FIRST
    finally:
        db.close()
