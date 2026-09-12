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
    assert "The 16 listings" in response.text
    assert "text-embedding-3-small" in response.text
    assert "grounded catalogue Q&amp;A uses gpt-4o-mini" in response.text
