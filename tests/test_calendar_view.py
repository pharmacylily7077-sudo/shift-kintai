import pytest
from fastapi.testclient import TestClient
from main import app
from seed import seed_data

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_data()

@pytest.fixture
def client():
    return TestClient(app)

def test_calendar_api_evaluation_colors_and_no_leak(client):
    """共有カレンダーAPIで各スタッフの評価カラーが反映され、給与情報が一切漏洩しないこと"""
    res = client.get("/api/calendar/monthly?year=2026&month=9")
    assert res.status_code == 200
    data = res.json()

    staff_colors = {s["full_name"]: s["color"] for s in data["staff"]}
    assert staff_colors["三宅 智之"] == "#064e3b"
    assert staff_colors["家田 知美"] == "#10b981"
    assert staff_colors["寺内 美和"] == "#2563eb"
    assert staff_colors["山中 久美"] == "#1e3a8a"
    assert staff_colors["小林 綾"] == "#8b5cf6"
    assert staff_colors["本間 まや"] == "#f43f5e"

    # プライバシー検証: 給与・時給・有休残の完全排除
    raw = res.text.lower()
    assert "wage" not in raw
    assert "salary" not in raw
    assert "hourly" not in raw
    assert "paid_leave" not in raw

def test_calendar_html_clean_white_and_print_layout(client):
    """共有カレンダーHTMLが白ベースで動的凡例を持ち、A4横印刷に対応していること"""
    res = client.get("/calendar")
    assert res.status_code == 200
    html = res.text

    assert "staff-legend" in html
    assert "window.print()" in html
    assert "リリー薬局" in html

    # 正社員/パートなどの格差・身分表記の完全排除
    assert "薬剤師（正）" not in html
    assert "薬剤師（パ）" not in html
    assert "調剤事務（正）" not in html
    assert "調剤事務（パ）" not in html
    assert "調剤補助（正）" not in html
    assert "調剤補助（パ）" not in html
