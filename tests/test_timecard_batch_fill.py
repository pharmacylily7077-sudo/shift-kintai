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


def test_batch_fill_realistic_minute_precision(admin_client):
    """小林・本間専用：一括打刻で00分や30分ではなくリアルな一桁分刻みの出退勤が生成されることの検証"""
    db = SessionLocal()
    try:
        # 小林さん (ID取得)
        kobayashi = db.query(models.User).filter(models.User.username == "kobayashi").first()
        assert kobayashi is not None
        k_id = kobayashi.id
    finally:
        db.close()

    # 2026年10月の一括シフトを先に生成
    admin_client.post("/api/admin/shifts/auto-generate", json={
        "year": 2026,
        "month": 10,
        "overwrite": True
    })

    # 一括打刻を実行 (overwrite_existing=True で全日生成)
    res_fill = admin_client.post("/api/admin/time-records/batch-fill", json={
        "user_id": k_id,
        "year": 2026,
        "month": 10,
        "overwrite_existing": True
    })
    assert res_fill.status_code == 200
    fill_data = res_fill.json()
    assert fill_data["success"] is True
    assert fill_data["filled_count"] > 0

    # タイムカードデータを取得して、生成された分数をチェック
    res_tc = admin_client.get(f"/api/admin/time-records/monthly?user_id={k_id}&year=2026&month=10")
    assert res_tc.status_code == 200
    tc_data = res_tc.json()
    assert tc_data["full_name"] == "小林 彩乃"

    worked_days = [d for d in tc_data["days"] if d["clock_in"] and d["clock_out"]]
    assert len(worked_days) > 0

    # すべての出勤・退勤の分数をチェック
    all_in_minutes = []
    all_out_minutes = []

    for wd in worked_days:
        cin = wd["clock_in"]  # "09:51" など
        cout = wd["clock_out"] # "19:14" など
        in_m = int(cin.split(":")[1])
        out_m = int(cout.split(":")[1])
        all_in_minutes.append(in_m)
        all_out_minutes.append(out_m)

    # 「ざっくりの30分、20分、00分」ばかりではないこと（一桁分刻みの自然な散らばりがあること）
    assert len(set(all_in_minutes)) >= 3, f"出勤分数が固定化されていないこと: {all_in_minutes}"
    assert len(set(all_out_minutes)) >= 3, f"退勤分数が固定化されていないこと: {all_out_minutes}"

    # 00分や30分ばかりではないことを確認
    non_round_in = [m for m in all_in_minutes if m not in [0, 30]]
    non_round_out = [m for m in all_out_minutes if m not in [0, 30]]
    assert len(non_round_in) == len(all_in_minutes), "出勤が自然な一桁分刻みであること"
    assert len(non_round_out) == len(all_out_minutes), "退勤が自然な一桁分刻みであること"


def test_single_time_record_update_and_clear(admin_client):
    """1分単位の手動修正およびクリアが正常に動作することの検証"""
    db = SessionLocal()
    try:
        honma = db.query(models.User).filter(models.User.username == "honma").first()
        assert honma is not None
        h_id = honma.id
    finally:
        db.close()

    # 本間さんの2026年10月5日を手動更新 (8:53 〜 18:17)
    res_update = admin_client.put("/api/admin/time-records/single", json={
        "user_id": h_id,
        "date": "2026-10-05",
        "clock_in": "08:53",
        "clock_out": "18:17",
        "break_minutes": 60,
        "clear": False
    })
    assert res_update.status_code == 200
    assert res_update.json()["success"] is True

    # 取得して確認
    res_tc = admin_client.get(f"/api/admin/time-records/monthly?user_id={h_id}&year=2026&month=10")
    assert res_tc.status_code == 200
    day_5 = next(d for d in res_tc.json()["days"] if d["day"] == 5)
    assert day_5["clock_in"] == "08:53"
    assert day_5["clock_out"] == "18:17"
    assert day_5["work_minutes"] == (18 * 60 + 17) - (8 * 60 + 53) - 60  # 564 - 60 = 504分 (8時間24分)


def test_timecard_csv_export(admin_client):
    """タイムカード出勤簿のCSVエクスポート検証"""
    db = SessionLocal()
    try:
        kobayashi = db.query(models.User).filter(models.User.username == "kobayashi").first()
        assert kobayashi is not None
        k_id = kobayashi.id
    finally:
        db.close()

    res_csv = admin_client.get(f"/api/admin/time-records/export-csv?user_id={k_id}&year=2026&month=10")
    assert res_csv.status_code == 200
    assert res_csv.headers["content-type"] == "text/csv; charset=utf-8"
    content = res_csv.content.decode("utf-8-sig")
    assert "勤務実績出勤簿（タイムカード）" in content
    assert "小林 彩乃" in content
    assert "合計出勤日数" in content
