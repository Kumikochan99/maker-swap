from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_home_page_loads() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Good tools deserve a second project." in response.text
    assert "CLASSGW_KEY" not in response.text


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_notes_page_is_real_and_truthful() -> None:
    response = client.get("/notes")

    assert response.status_code == 200
    assert "What this demo is - and is not." in response.text
    assert 'id="built-for"' in response.text
    assert 'id="seeded-limited"' in response.text
    assert 'id="ai-tools"' in response.text
    assert 'id="excluded"' in response.text
    assert 'id="known-issues"' in response.text
    assert "16 seeded listings" in response.text
    assert "openai/text-embedding-3-small" in response.text
    assert "openai/gpt-4o-mini" in response.text
    assert "gpt-5.6-sol max" in response.text
    assert "Budget language is approximate." in response.text
    assert "CLASSGW_KEY" not in response.text
