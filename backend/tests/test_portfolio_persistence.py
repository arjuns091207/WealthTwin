
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


def test_delete_portfolio_removes_saved_data(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Portfolio to delete",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "100",
                }
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/portfolio/{portfolio_id}")

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/v1/portfolio/{portfolio_id}").status_code == 404
    assert all(
        item["id"] != portfolio_id
        for item in client.get("/api/v1/portfolio").json()
    )


def test_delete_unknown_portfolio_returns_404(client: TestClient):
    response = client.delete("/api/v1/portfolio/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"


def test_delete_portfolio_with_positions(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Portfolio with positions",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "100",
                },
                {
                    "symbol": "MSFT",
                    "quantity": "3",
                    "price_per_unit": "200",
                },
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.delete(f"/api/v1/portfolio/{portfolio_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/portfolio/{portfolio_id}").status_code == 404


def test_value_saved_portfolio_calculates_market_values(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Valuation portfolio",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "150.25",
                },
                {
                    "symbol": "BOND",
                    "quantity": "3",
                    "price_per_unit": "100",
                },
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.get(
        f"/api/v1/portfolio/{portfolio_id}/valuation"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["portfolio_id"] == portfolio_id
    assert data["portfolio_name"] == "Valuation portfolio"
    assert data["position_count"] == 2
    values = {item["symbol"]: item["market_value"] for item in data["positions"]}
    assert values["AAPL"] == 300.5
    assert values["BOND"] == 300
    assert data["total_market_value"] == 600.5


def test_value_saved_portfolio_returns_zero_for_empty_portfolio(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty portfolio", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/valuation"
    )

    assert response.status_code == 200
    assert response.json()["position_count"] == 0
    assert response.json()["positions"] == []
    assert response.json()["total_market_value"] == 0


def test_value_unknown_portfolio_returns_404(client: TestClient):
    response = client.get("/api/v1/portfolio/999999/valuation")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_update_portfolio_renames_and_preserves_positions(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Old name",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "150",
                }
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.patch(
        f"/api/v1/portfolio/{portfolio_id}",
        json={"name": "  New name  "},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New name"
    assert len(data["positions"]) == 1
    assert data["positions"][0]["symbol"] == "AAPL"
    assert data["positions"][0]["quantity"] == "2.00000000"


@pytest.mark.parametrize("name", ["", "   "])
def test_update_portfolio_rejects_blank_name(client: TestClient, name: str):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Existing name", "positions": []},
    )
    assert created.status_code == 201

    response = client.patch(
        f"/api/v1/portfolio/{created.json()['id']}",
        json={"name": name},
    )

    assert response.status_code == 422


def test_update_unknown_portfolio_returns_404(client: TestClient):
    response = client.patch(
        "/api/v1/portfolio/999999",
        json={"name": "New name"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_add_position_to_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Growth portfolio",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "2",
                    "price_per_unit": "100",
                }
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.post(
        f"/api/v1/portfolio/{portfolio_id}/positions",
        json={
            "symbol": "MSFT",
            "quantity": "3",
            "price_per_unit": "200",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == portfolio_id
    assert {item["symbol"] for item in data["positions"]} == {"AAPL", "MSFT"}
    assert len(data["positions"]) == 2


def test_add_duplicate_position_returns_409(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Duplicate test",
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "1",
                    "price_per_unit": "100",
                }
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.post(
        f"/api/v1/portfolio/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "quantity": "2",
            "price_per_unit": "150",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Portfolio already contains this symbol"
    saved = client.get(f"/api/v1/portfolio/{portfolio_id}").json()
    assert len(saved["positions"]) == 1


def test_add_position_to_unknown_portfolio_returns_404(client: TestClient):
    response = client.post(
        "/api/v1/portfolio/999999/positions",
        json={
            "symbol": "AAPL",
            "quantity": "1",
            "price_per_unit": "100",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"


def test_add_position_rejects_invalid_financial_values(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Validation test", "positions": []},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.post(
        f"/api/v1/portfolio/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "quantity": "0",
            "price_per_unit": "100",
        },
    )

    assert response.status_code == 422

def test_remove_position_from_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Holdings removal test",
            "positions": [
                {"symbol": "AAPL", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "MSFT", "quantity": "3", "price_per_unit": "200"},
            ],
        },
    )
    assert created.status_code == 201
    data = created.json()
    portfolio_id = data["id"]
    aapl = next(p for p in data["positions"] if p["symbol"] == "AAPL")

    response = client.delete(
        f"/api/v1/portfolio/{portfolio_id}/positions/{aapl['id']}"
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == portfolio_id
    assert [p["symbol"] for p in updated["positions"]] == ["MSFT"]
    assert client.get(f"/api/v1/portfolio/{portfolio_id}").status_code == 200


def test_remove_position_from_unknown_portfolio_returns_404(
    client: TestClient,
):
    response = client.delete("/api/v1/portfolio/999999/positions/1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"


def test_remove_unknown_position_returns_404(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Position not found test", "positions": []},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/portfolio/{portfolio_id}/positions/999999"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Position not found in this portfolio"


def test_cannot_remove_position_from_another_portfolio(client: TestClient):
    first = client.post(
        "/api/v1/portfolio",
        json={
            "name": "First portfolio",
            "positions": [
                {"symbol": "AAPL", "quantity": "1", "price_per_unit": "100"}
            ],
        },
    )
    second = client.post(
        "/api/v1/portfolio",
        json={"name": "Second portfolio", "positions": []},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    position_id = first.json()["positions"][0]["id"]
    second_id = second.json()["id"]

    response = client.delete(
        f"/api/v1/portfolio/{second_id}/positions/{position_id}"
    )

    assert response.status_code == 404
    assert client.get(
        f"/api/v1/portfolio/{first.json()['id']}"
    ).json()["positions"][0]["symbol"] == "AAPL"

def test_portfolio_allocation_calculates_weights(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Allocation test",
            "positions": [
                {"symbol": "AAPL", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "MSFT", "quantity": "1", "price_per_unit": "200"},
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.get(
        f"/api/v1/portfolio/{portfolio_id}/allocation"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_market_value"] == 400
    weights = {item["symbol"]: item["allocation_pct"] for item in data["positions"]}
    assert weights["AAPL"] == 50
    assert weights["MSFT"] == 50
    assert sum(weights.values()) == 100


def test_portfolio_allocation_handles_zero_market_value(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Zero value allocation",
            "positions": [
                {"symbol": "CASH", "quantity": "5", "price_per_unit": "0"}
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/allocation"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_market_value"] == 0
    assert data["positions"][0]["allocation_pct"] == 0


def test_portfolio_allocation_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/allocation")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"
