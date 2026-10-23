
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


def test_list_portfolios_returns_saved_portfolios(client: TestClient):
    first = client.post(
        "/api/v1/portfolio",
        json={"name": "First portfolio", "positions": []},
    )
    second = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Second portfolio",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "100",
                }
            ],
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get("/api/v1/portfolio")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {portfolio["name"] for portfolio in data} == {
        "First portfolio",
        "Second portfolio",
    }
    assert all("positions" in portfolio for portfolio in data)


def test_list_portfolios_supports_pagination(client: TestClient):
    for name in ["Portfolio A", "Portfolio B", "Portfolio C"]:
        response = client.post(
            "/api/v1/portfolio",
            json={"name": name, "positions": []},
        )
        assert response.status_code == 201

    first_page = client.get("/api/v1/portfolio?skip=0&limit=2")
    second_page = client.get("/api/v1/portfolio?skip=2&limit=2")

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 1

    first_ids = {portfolio["id"] for portfolio in first_page.json()}
    second_ids = {portfolio["id"] for portfolio in second_page.json()}
    assert first_ids.isdisjoint(second_ids)


def test_list_portfolios_rejects_invalid_pagination(client: TestClient):
    assert client.get("/api/v1/portfolio?skip=-1").status_code == 422
    assert client.get("/api/v1/portfolio?limit=0").status_code == 422
    assert client.get("/api/v1/portfolio?limit=101").status_code == 422


def test_list_portfolios_returns_empty_list_when_no_data(client: TestClient):
    response = client.get("/api/v1/portfolio")

    assert response.status_code == 200
    assert response.json() == []
