import pytest
from fastapi.testclient import TestClient
from main import app
from seed import seed_data
from routers.me_router import GENTLE_THOUGHTS

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_data()

@pytest.fixture
def auth_client():
    client = TestClient(app)
    # 小林さんでログイン
    res = client.post("/api/auth/login", json={
        "position": "ASSISTANT",
        "username": "kobayashi",
        "password": "kobayashi1234"
    })
    assert res.status_code == 200
    return client

def test_gentle_thoughts_api(auth_client):
    """恋人に伝えるかのような24の感謝英語フレーズAPIの検証"""
    res = auth_client.get("/api/me/gentle-thought")
    assert res.status_code == 200
    data = res.json()
    assert data["thought"] in GENTLE_THOUGHTS
    assert data["count"] == 24
    assert len(data["all_thoughts"]) == 24

def test_myroom_dashboard_and_theme_palette(auth_client):
    """ダッシュボードにgentle_thoughtおよび5色パレットが含まれていること"""
    res = auth_client.get("/api/me/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert "gentle_thought" in data
    assert data["gentle_thought"] in GENTLE_THOUGHTS
    
    palettes = [p["id"] for p in data["theme_palettes"]]
    assert "rose" in palettes
    assert "blue" in palettes
    assert "mint" in palettes
    assert "champagne" in palettes
    assert "lavender" in palettes

    # テーマ変更APIの検証
    res_theme = auth_client.put("/api/me/theme", json={
        "theme_color": "rose",
        "theme_bg": "simple"
    })
    assert res_theme.status_code == 200
    assert res_theme.json()["theme_color"] == "rose"

def test_myroom_html_french_aesthetic(auth_client):
    """HTML内にLa Douce Gestion, A Gentle Thought, 5色パレットが存在し、ダサい標語が皆無であること"""
    res = auth_client.get("/me")
    assert res.status_code == 200
    html = res.text

    assert "La Douce Gestion" in html
    assert "A Gentle Thought" in html
    assert "setTheme('rose')" in html
    assert "setTheme('blue')" in html
    assert "setTheme('mint')" in html
    assert "setTheme('champagne')" in html
    assert "setTheme('lavender')" in html

    # ダサい言葉・標語の完全排除検証
    assert "今月の言葉" not in html
    assert "今月のお知らせ" not in html
