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
def admin_client(client):
    r = client.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "miyake",
        "password": "admin123"
    })
    assert r.status_code == 200
    return client


def test_get_staff_conditions(admin_client):
    res = admin_client.get("/api/admin/staff/conditions")
    assert res.status_code == 200
    data = res.json()
    assert "staff" in data
    assert len(data["staff"]) == 6
    names = [s["full_name"] for s in data["staff"]]
    assert "三宅 智之" in names
    assert "小林 彩乃" in names
    assert "家田 知美" in names


def test_update_staff_condition(admin_client):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "terauchi").first()
        assert user is not None
        user_id = user.id
    finally:
        db.close()

    # 寺内さんの定休日に水曜日(2)を追加、時給を1600円に変更
    payload = {
        "default_shift": "FIRST",
        "fixed_off_weekdays": "1,2,6", # 火・水・日
        "hourly_wage": 1600,
        "paid_leave_remaining": 8.5
    }
    res = admin_client.put(f"/api/admin/staff/{user_id}/condition", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["default_shift"] == "FIRST"
    assert res_data["fixed_off_weekdays"] == "1,2,6"
    assert res_data["hourly_wage"] == 1600
    assert res_data["paid_leave_remaining"] == 8.5

    # 取得して確認
    res_get = admin_client.get("/api/admin/staff/conditions")
    assert res_get.status_code == 200
    updated = next(s for s in res_get.json()["staff"] if s["id"] == user_id)
    assert updated["default_shift"] == "FIRST"
    assert "水" in updated["fixed_off_labels"]
    assert updated["hourly_wage"] == 1600

    # 元に戻す
    admin_client.put(f"/api/admin/staff/{user_id}/condition", json={
        "default_shift": "FULL",
        "fixed_off_weekdays": "1,6",
        "hourly_wage": 0,
        "paid_leave_remaining": 0.0
    })


def test_auto_generate_reflects_conditions(admin_client):
    # 自動生成実行 (2026年10月)
    res_gen = admin_client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 10,
        "overwrite": True
    })
    assert res_gen.status_code == 200
    assert res_gen.json()["success"] is True

    # 2026年10月のカレンダーを取得
    res_cal = admin_client.get("/api/calendar/monthly?year=2026&month=10")
    assert res_cal.status_code == 200
    cal_data = res_cal.json()
    assert cal_data["year"] == 2026
    assert cal_data["month"] == 10

    # 日曜（10/4）は全員シフトなし
    oct_4 = next(d for d in cal_data["days"] if d["day"] == 4)
    assert oct_4["is_sunday"] is True
    assert len(oct_4["shifts"]) == 0


def test_share_text_and_backup_export(admin_client):
    # LINE共有テキスト生成
    res_text = admin_client.get("/api/admin/shifts/share-text?year=2026&month=10")
    assert res_text.status_code == 200
    text_data = res_text.json()
    assert "full_text" in text_data
    assert "【リリー薬局】" in text_data["full_text"]
    assert len(text_data["by_staff"]) == 6

    # ZIPバックアップ
    res_zip = admin_client.get("/api/admin/backup/export")
    assert res_zip.status_code == 200
    assert res_zip.headers["content-type"] == "application/zip"
    assert len(res_zip.content) > 0


def test_compliance_paid_leave(admin_client):
    res_comp = admin_client.get("/api/admin/compliance/paid-leave?year=2026")
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["year"] == 2026
    assert len(comp_data["staff"]) == 6
