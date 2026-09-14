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
    assert "What I built and what is still limited." in response.text
    assert "Build notes / Current demo" in response.text
    assert 'id="built-for"' in response.text
    assert 'id="seeded-limited"' in response.text
    assert 'id="ai-tools"' in response.text
    assert 'id="excluded"' in response.text
    assert 'id="known-issues"' in response.text
    assert "16 seeded listings" in response.text
    assert "openai/text-embedding-3-small" in response.text
    assert "openai/gpt-4o-mini" in response.text
    assert "gpt-5.6-sol max" in response.text
    assert "Price and budget words are not hard filters." in response.text
    assert '"portable musical instrument around $100"' in response.text
    assert "S$420 Original Prusa MINI+" in response.text
    assert "S$380 Bambu Lab A1 mini" in response.text
    assert "Condition words are not hard filters." in response.text
    assert '"portable gear in mint condition"' in response.text
    assert "Resolved after the audit: search availability." in response.text
    assert "13 listings Available, two Reserved, and one Sold" in response.text
    assert "Listings in the same category reuse that set" in response.text
    assert "Checkout is fully simulated" in response.text
    assert "processes no payment and stores no reservation" in response.text
    assert "order endpoint, stored reservation, or inventory update" in response.text
    assert "search relevance and grounded Q&amp;A instead" in response.text
    assert "Available Raspberry Pi 4 Workbench Set at S$95" in response.text
    assert "great choice for beginners and user-friendly" in response.text
    assert "390 px and 430 px widths" in response.text
    assert "I did not test this build on a physical phone" in response.text
    assert "The bare <code>cg_</code> prefix" in response.text
    assert "plan.md" in response.text
    assert "decisions.md" in response.text
    assert "credential-shaped value" in response.text
    assert "—" not in response.text
    assert "CLASSGW_KEY" not in response.text
