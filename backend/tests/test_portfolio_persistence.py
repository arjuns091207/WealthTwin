
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.db import models  # Register ORM models with Base.metadata


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_create_portfolio_persists_positions(client: TestClient):
    response = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Long-term investments",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2.5",
                    "price_per_unit": "200",
                },
                {
                    "symbol": "MSFT",
                    "quantity": "3",
                    "price_per_unit": "400",
                },
            ],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Long-term investments"
    assert len(data["positions"]) == 2
    assert data["positions"][0]["symbol"] == "AAPL"
    assert data["positions"][0]["quantity"] == "2.50000000"


def test_get_portfolio_returns_saved_data(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Retirement",
            "positions": [
                {
                    "symbol": "BOND",
                    "quantity": "10",
                    "price_per_unit": "99.50",
                }
            ],
        },
    )
    assert created.status_code == 201

    portfolio_id = created.json()["id"]
    response = client.get(f"/api/v1/portfolio/{portfolio_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Retirement"
    assert response.json()["positions"][0]["symbol"] == "BOND"


def test_get_unknown_portfolio_returns_404(client: TestClient):
    response = client.get("/api/v1/portfolio/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"


@pytest.mark.parametrize("name", ["", "   "])
def test_create_portfolio_rejects_blank_name(client: TestClient, name: str):
    response = client.post(
        "/api/v1/portfolio",
        json={"name": name, "positions": []},
    )

    assert response.status_code == 422


def test_create_portfolio_rejects_duplicate_symbols(client: TestClient):
    response = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Duplicate holdings",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "1",
                    "price_per_unit": "100",
                },
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "200",
                },
            ],
        },
    )

    assert response.status_code == 409
