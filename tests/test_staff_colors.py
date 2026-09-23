import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
import models
from seed import seed_data

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_data()

@pytest.fixture
def client():
    return TestClient(app)

def test_six_staff_evaluation_colors_and_full_names(client):
    """6名のフルネームと評価カラー（緑・青・赤/紫グラデーション）の検証"""
    expected = {
        "miyake": {"name": "三宅 興之", "color": "#064e3b", "pos": "PHARMACIST"},
        "ieda": {"name": "家田 知美", "color": "#10b981", "pos": "PHARMACIST"},
        "terauchi": {"name": "寺内 美和", "color": "#2563eb", "pos": "CLERK"},
        "yamanaka": {"name": "山中 久美", "color": "#1e3a8a", "pos": "CLERK"},
        "kobayashi": {"name": "小林 綾", "color": "#8b5cf6", "pos": "ASSISTANT"},
        "honma": {"name": "本間 まや", "color": "#f43f5e", "pos": "ASSISTANT"},
    }

    # 1. 各ポジションのスタッフリストAPI検証
    for pos in ["PHARMACIST", "CLERK", "ASSISTANT"]:
        res = client.get(f"/api/auth/staff-list?position={pos}")
        assert res.status_code == 200
        staff_data = res.json()
        assert len(staff_data) == 2
        for s in staff_data:
            u = s["username"]
            assert u in expected
            assert s["full_name"] == expected[u]["name"]
            assert s["evaluation_color"] == expected[u]["color"]
            assert s["position"] == expected[u]["pos"]

    # 2. ログイン認証の検証（三宅薬局長と小林さん）
    res_miyake = client.post("/api/auth/login", json={
        "position": "PHARMACIST",
        "username": "miyake",
        "password": "admin123"
    })
    assert res_miyake.status_code == 200
    assert res_miyake.json()["full_name"] == "三宅 興之"

    res_kobayashi = client.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi1234"
    })
    assert res_kobayashi.status_code == 200
    assert res_kobayashi.json()["full_name"] == "小林 綾"
