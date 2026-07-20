from fastapi.testclient import TestClient

from app.main import app, init_db


client = TestClient(app)
init_db()


def headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/demo")
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] in {"sqlite", "postgres"}


def test_rejects_unsupported_file() -> None:
    response = client.post("/api/v1/documents", headers=headers(), files={"file": ("script.exe", b"bad", "application/octet-stream")})
    assert response.status_code == 415


def test_documents_require_authentication() -> None:
    response = client.get("/api/v1/documents")
    assert response.status_code == 401


def test_demo_user_can_read_scoped_workspace() -> None:
    response = client.get("/api/v1/analytics/overview", headers=headers())
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"documents_uploaded", "high_risk_documents", "upcoming_deadlines", "protection_score", "categories", "monthly_uploads"}


def test_registration_creates_a_separate_workspace() -> None:
    response = client.post("/api/v1/auth/register", json={"email": "test-owner@example.com", "name": "Test Owner", "password": "secure-password"})
    assert response.status_code in {201, 409}
    if response.status_code == 201:
        assert response.json()["user"]["organization_id"] != "demo-org"


def test_features_endpoint() -> None:
    response = client.get("/api/v1/features")
    assert response.status_code == 200
    assert "pipeline_stages" in response.json()
    assert len(response.json()["pipeline_stages"]) >= 8


def test_notifications_require_auth() -> None:
    response = client.get("/api/v1/notifications")
    assert response.status_code == 401
