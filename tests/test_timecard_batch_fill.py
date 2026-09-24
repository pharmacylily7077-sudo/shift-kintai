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


def test_batch_fill_realistic_minute_and_second_precision(admin_client):
    """小林・本間専用：一括打刻で00分や30分ではなくリアルな一桁分刻み＋秒単位ゆらぎの出退勤が生成されることの検証"""
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

    # タイムカードデータを取得して、生成された分数・秒数をチェック
    res_tc = admin_client.get(f"/api/admin/time-records/monthly?user_id={k_id}&year=2026&month=10")
    assert res_tc.status_code == 200
    tc_data = res_tc.json()
    assert tc_data["full_name"] == "小林 彩乃"

    worked_days = [d for d in tc_data["days"] if d["clock_in"] and d["clock_out"]]
    assert len(worked_days) > 0

    # すべての出勤・退勤の分数・秒数をチェック
    all_in_minutes = []
    all_out_minutes = []
    all_in_seconds = []
    all_out_seconds = []

    for wd in worked_days:
        cin = wd["clock_in"]  # "09:51:34" など (HH:MM:SS)
        cout = wd["clock_out"] # "19:14:22" など (HH:MM:SS)
        cin_parts = cin.split(":")
        cout_parts = cout.split(":")
        assert len(cin_parts) == 3, f"出勤時刻が秒まで含まれていること: {cin}"
        assert len(cout_parts) == 3, f"退勤時刻が秒まで含まれていること: {cout}"

        all_in_minutes.append(int(cin_parts[1]))
        all_in_seconds.append(int(cin_parts[2]))
        all_out_minutes.append(int(cout_parts[1]))
        all_out_seconds.append(int(cout_parts[2]))

    # 「ざっくりの30分、20分、00分」ばかりではないこと（一桁分刻みの自然な散らばりがあること）
    assert len(set(all_in_minutes)) >= 3, f"出勤分数が固定化されていないこと: {all_in_minutes}"
    assert len(set(all_out_minutes)) >= 3, f"退勤分数が固定化されていないこと: {all_out_minutes}"

    # 秒単位のゆらぎが存在すること（秒がすべて同一・00ではないこと）
    assert len(set(all_in_seconds)) >= 3, f"出勤秒数がランダムに揺らいでいること: {all_in_seconds}"
    assert len(set(all_out_seconds)) >= 3, f"退勤秒数がランダムに揺らいでいること: {all_out_seconds}"

    # 00分や30分ばかりではないことを確認
    non_round_in = [m for m in all_in_minutes if m not in [0, 30]]
    non_round_out = [m for m in all_out_minutes if m not in [0, 30]]
    assert len(non_round_in) == len(all_in_minutes), "出勤が自然な一桁分刻みであること"
    assert len(non_round_out) == len(all_out_minutes), "退勤が自然な一桁分刻みであること"


def test_single_time_record_update_and_clear(admin_client):
    """秒単位の手動修正およびクリアが正常に動作することの検証"""
    db = SessionLocal()
    try:
        honma = db.query(models.User).filter(models.User.username == "honma").first()
        assert honma is not None
        h_id = honma.id
    finally:
        db.close()

    # 本間さんの2026年10月5日を手動更新 (8:53:42 〜 18:17:15)
    res_update = admin_client.put("/api/admin/time-records/single", json={
        "user_id": h_id,
        "date": "2026-10-05",
        "clock_in": "08:53:42",
        "clock_out": "18:17:15",
        "break_minutes": 60,
        "clear": False
    })
    assert res_update.status_code == 200
    assert res_update.json()["success"] is True

    # 取得して確認（秒まで完全反映）
    res_tc = admin_client.get(f"/api/admin/time-records/monthly?user_id={h_id}&year=2026&month=10")
    assert res_tc.status_code == 200
    day_5 = next(d for d in res_tc.json()["days"] if d["day"] == 5)
    assert day_5["clock_in"] == "08:53:42"
    # 8:53:42〜18:17:15 = 9時間23分33秒(563.55分) - 休憩60分 = 503分
    assert day_5["work_minutes"] == 503


def test_timecard_csv_export(admin_client):
    """タイムカード出勤簿のCSVエクスポート検証（秒まで出力）"""
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
    # 秒付き時刻（例: 09:xx:xx）が含まれていること
    import re
    assert re.search(r"\d{2}:\d{2}:\d{2}", content) is not None, "CSV内に秒単位の出退勤時刻が存在すること"
