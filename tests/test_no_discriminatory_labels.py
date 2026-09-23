import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from main import app
from seed import seed_data

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_data()

@pytest.fixture
def client():
    return TestClient(app)

def test_templates_have_no_discriminatory_labels():
    """HTMLテンプレート全体から『正社員』『パート』という身分差別ラベルが完全に排除されていること"""
    template_dir = Path("templates")
    html_files = list(template_dir.glob("*.html"))
    assert len(html_files) > 0

    forbidden_terms = ["正社員", "パート"]
    violations = []

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        for term in forbidden_terms:
            if term in content:
                violations.append(f"{html_file.name} に禁止語 '{term}' が含まれています")

    assert not violations, f"テンプレート内に禁止語が検出されました:\n" + "\n".join(violations)

def test_api_responses_have_no_discriminatory_labels(client):
    """公開APIのレスポンスに『正社員』『パート』が含まれず、職能名に統一されていること"""
    # 1. カレンダー
    res_cal = client.get("/api/calendar/monthly?year=2026&month=9")
    assert res_cal.status_code == 200
    assert "正社員" not in res_cal.text
    assert "パート" not in res_cal.text

    # 2. スタッフリスト
    for pos in ["PHARMACIST", "CLERK", "ASSISTANT"]:
        res_staff = client.get(f"/api/auth/staff-list?position={pos}")
        assert res_staff.status_code == 200
        assert "正社員" not in res_staff.text
        assert "パート" not in res_staff.text
