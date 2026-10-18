from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to WealthTwin API"
    assert response.json()["version"] == "0.1.0"


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "wealthtwin"
    assert "timestamp" in response.json()


def test_database_health_success(monkeypatch):
    monkeypatch.setattr(
        "app.main.check_database_connection",
        lambda: True,
    )

    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["database"] == "postgresql"
    assert response.json()["query_test"] == "passed"


def test_database_health_failure(monkeypatch):
    monkeypatch.setattr(
        "app.main.check_database_connection",
        lambda: False,
    )

    response = client.get("/health/database")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database connection failed"