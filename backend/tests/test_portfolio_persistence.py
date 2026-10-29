
from collections.abc import Generator
import csv

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

def test_portfolio_summary_returns_valuation_metrics(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Summary test",
            "positions": [
                {"symbol": "AAPL", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "MSFT", "quantity": "3", "price_per_unit": "200"},
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.get(f"/api/v1/portfolio/{portfolio_id}/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["portfolio_name"] == "Summary test"
    assert data["position_count"] == 2
    assert data["total_market_value"] == 800
    assert data["largest_position"]["symbol"] == "MSFT"
    assert data["largest_position"]["market_value"] == 600
    assert data["largest_position"]["allocation_pct"] == 75


def test_portfolio_summary_handles_empty_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty summary", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/summary"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 0
    assert data["total_market_value"] == 0
    assert data["largest_position"] is None


def test_portfolio_summary_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/summary")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_risk_reports_concentration(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Risk test",
            "positions": [
                {"symbol": "AAPL", "quantity": "6", "price_per_unit": "100"},
                {"symbol": "MSFT", "quantity": "3", "price_per_unit": "100"},
                {"symbol": "NVDA", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "GOOG", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/risk"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_market_value"] == 1100
    assert data["position_count"] == 4
    assert data["largest_position"]["symbol"] == "AAPL"
    assert data["largest_allocation_pct"] == 600 / 11
    assert data["top_three_allocation_pct"] == 1000 / 11


def test_portfolio_risk_handles_empty_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty risk", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/risk"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 0
    assert data["total_market_value"] == 0
    assert data["largest_position"] is None
    assert data["largest_allocation_pct"] == 0
    assert data["top_three_allocation_pct"] == 0


def test_portfolio_risk_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/risk")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_diversification_calculates_hhi(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Diversification test",
            "positions": [
                {"symbol": "AAA", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "BBB", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "CCC", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "DDD", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/diversification"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 4
    assert data["total_market_value"] == 400
    assert data["herfindahl_hirschman_index"] == 0.25
    assert data["effective_number_of_positions"] == 4


def test_portfolio_diversification_handles_empty_portfolio(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty diversification", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/diversification"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 0
    assert data["total_market_value"] == 0
    assert data["herfindahl_hirschman_index"] == 0
    assert data["effective_number_of_positions"] == 0


def test_portfolio_diversification_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/diversification")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_analytics_combines_metrics(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Analytics overview",
            "positions": [
                {"symbol": "AAA", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "BBB", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "CCC", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "DDD", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/analytics"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["portfolio_name"] == "Analytics overview"
    assert data["position_count"] == 4
    assert data["total_market_value"] == 400
    assert data["largest_allocation_pct"] == 25
    assert data["top_three_allocation_pct"] == 75
    assert data["herfindahl_hirschman_index"] == 0.25
    assert data["effective_number_of_positions"] == 4


def test_portfolio_analytics_handles_empty_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty analytics", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/analytics"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 0
    assert data["total_market_value"] == 0
    assert data["largest_position"] is None
    assert data["largest_allocation_pct"] == 0
    assert data["top_three_allocation_pct"] == 0
    assert data["herfindahl_hirschman_index"] == 0
    assert data["effective_number_of_positions"] == 0


def test_portfolio_analytics_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/analytics")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_comparison_returns_metric_differences(client: TestClient):
    first = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Comparison A",
            "positions": [
                {"symbol": "AAA", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "BBB", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    second = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Comparison B",
            "positions": [
                {"symbol": "CCC", "quantity": "1", "price_per_unit": "300"},
            ],
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/compare/{first.json()['id']}/{second.json()['id']}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_portfolio"]["total_market_value"] == 200
    assert data["first_portfolio"]["position_count"] == 2
    assert data["first_portfolio"]["herfindahl_hirschman_index"] == 0.5
    assert data["first_portfolio"]["effective_number_of_positions"] == 2
    assert data["second_portfolio"]["total_market_value"] == 300
    assert data["second_portfolio"]["position_count"] == 1
    assert data["second_portfolio"]["herfindahl_hirschman_index"] == 1
    assert data["second_portfolio"]["effective_number_of_positions"] == 1
    assert data["market_value_difference"] == -100


def test_portfolio_comparison_returns_404_if_either_is_missing(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Existing comparison portfolio", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/compare/{created.json()['id']}/999999"
    )

    assert response.status_code == 404
    assert "Portfolio not found" in response.json()["detail"]


def test_portfolio_comparison_rejects_same_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Same portfolio", "positions": []},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.get(
        f"/api/v1/portfolio/compare/{portfolio_id}/{portfolio_id}"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Choose two different portfolios to compare"



def test_portfolio_allocation_bands_classifies_positions(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Allocation bands",
            "positions": [
                {"symbol": "A", "quantity": "6", "price_per_unit": "100"},
                {"symbol": "B", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "C", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "D", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/allocation-bands"
    )

    assert response.status_code == 200
    data = response.json()
    assert {p["symbol"] for p in data["bands"]["dominant"]} == {"A", "B"}
    assert {p["symbol"] for p in data["bands"]["medium"]} == {"C", "D"}
    assert data["bands"]["small"] == []


def test_portfolio_allocation_bands_supports_custom_thresholds(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Custom thresholds",
            "positions": [
                {"symbol": "A", "quantity": "7", "price_per_unit": "100"},
                {"symbol": "B", "quantity": "3", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/allocation-bands",
        params={
            "dominant_threshold_pct": 60,
            "medium_threshold_pct": 20,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert [p["symbol"] for p in data["bands"]["dominant"]] == ["A"]
    assert [p["symbol"] for p in data["bands"]["medium"]] == ["B"]


def test_portfolio_allocation_bands_rejects_invalid_thresholds(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Invalid thresholds", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/allocation-bands",
        params={
            "dominant_threshold_pct": 10,
            "medium_threshold_pct": 10,
        },
    )

    assert response.status_code == 422


def test_portfolio_allocation_bands_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/allocation-bands")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_rebalance_calculates_buy_sell_and_hold(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Rebalance test",
            "positions": [
                {"symbol": "A", "quantity": "8", "price_per_unit": "100"},
                {"symbol": "B", "quantity": "2", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/portfolio/{created.json()['id']}/rebalance",
        json={"target_allocations": {"A": "50", "B": "50"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_market_value"] == 1000.0
    recommendations = {item["symbol"]: item for item in data["recommendations"]}
    assert recommendations["A"]["action"] == "sell"
    assert recommendations["A"]["trade_value"] == -300.0
    assert recommendations["B"]["action"] == "buy"
    assert recommendations["B"]["trade_value"] == 300.0


def test_portfolio_rebalance_rejects_targets_not_summing_to_100(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Invalid targets",
            "positions": [
                {"symbol": "A", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/portfolio/{created.json()['id']}/rebalance",
        json={"target_allocations": {"A": "80"}},
    )

    assert response.status_code == 422


def test_portfolio_rebalance_rejects_unknown_symbols(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Unknown target",
            "positions": [
                {"symbol": "A", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/portfolio/{created.json()['id']}/rebalance",
        json={"target_allocations": {"UNKNOWN": "100"}},
    )

    assert response.status_code == 422


def test_portfolio_rebalance_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.post(
        "/api/v1/portfolio/999999/rebalance",
        json={"target_allocations": {"A": "100"}},
    )

    assert response.status_code == 404


def test_portfolio_rebalance_rejects_zero_market_value(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Zero value",
            "positions": [
                {"symbol": "A", "quantity": "1", "price_per_unit": "0"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/portfolio/{created.json()['id']}/rebalance",
        json={"target_allocations": {"A": "100"}},
    )

    assert response.status_code == 422


def test_portfolio_distribution_calculates_value_statistics(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Distribution test",
            "positions": [
                {"symbol": "AAA", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "BBB", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "CCC", "quantity": "3", "price_per_unit": "100"},
                {"symbol": "DDD", "quantity": "4", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/distribution"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 4
    assert data["total_market_value"] == 1000
    assert data["minimum_position_value"] == 100
    assert data["maximum_position_value"] == 400
    assert data["mean_position_value"] == 250
    assert data["median_position_value"] == 250
    assert data["position_value_range"] == 300


def test_portfolio_distribution_handles_empty_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty distribution", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/distribution"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 0
    assert data["total_market_value"] == 0
    assert data["minimum_position_value"] == 0
    assert data["maximum_position_value"] == 0
    assert data["mean_position_value"] == 0
    assert data["median_position_value"] == 0
    assert data["position_value_range"] == 0


def test_portfolio_distribution_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/distribution")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"



def test_portfolio_csv_export_returns_sorted_holdings(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "CSV export",
            "positions": [
                {"symbol": "ZETA", "quantity": "2", "price_per_unit": "15.50"},
                {"symbol": "ALPHA", "quantity": "3", "price_per_unit": "20"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/export"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]

    rows = list(csv.reader(response.text.splitlines()))
    assert rows[0] == ["symbol", "quantity", "price_per_unit", "market_value"]
    assert rows[1] == ["ALPHA", "3.00000000", "20.00000000", "60.0000000000000000"]
    assert rows[2] == ["ZETA", "2.00000000", "15.50000000", "31.0000000000000000"]


def test_portfolio_csv_export_handles_empty_portfolio(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Empty CSV", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/export"
    )

    assert response.status_code == 200
    rows = list(csv.reader(response.text.splitlines()))
    assert rows == [["symbol", "quantity", "price_per_unit", "market_value"]]


def test_portfolio_csv_export_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/export")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"



def test_portfolio_position_search_filters_by_prefix_and_value(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Position search",
            "positions": [
                {"symbol": "AAPL", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "AMZN", "quantity": "1", "price_per_unit": "300"},
                {"symbol": "MSFT", "quantity": "4", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    response = client.get(
        f"/api/v1/portfolio/{portfolio_id}/positions/search",
        params={
            "symbol_prefix": "a",
            "min_market_value": "200",
            "max_market_value": "300",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result_count"] == 2
    assert [item["symbol"] for item in data["positions"]] == ["AAPL", "AMZN"]
    assert [item["market_value"] for item in data["positions"]] == [200, 300]


def test_portfolio_position_search_returns_empty_results(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "No matching positions",
            "positions": [
                {"symbol": "AAPL", "quantity": "1", "price_per_unit": "100"},
            ],
        },
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/positions/search",
        params={"symbol_prefix": "ZZZ"},
    )

    assert response.status_code == 200
    assert response.json()["result_count"] == 0
    assert response.json()["positions"] == []


def test_portfolio_position_search_rejects_invalid_value_bounds(
    client: TestClient,
):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Invalid search", "positions": []},
    )
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/portfolio/{created.json()['id']}/positions/search",
        params={"min_market_value": "500", "max_market_value": "100"},
    )

    assert response.status_code == 422


def test_portfolio_position_search_returns_404_for_unknown_portfolio(
    client: TestClient,
):
    response = client.get("/api/v1/portfolio/999999/positions/search")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"

def test_portfolio_position_search_paginates_results(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={
            "name": "Position pagination",
            "positions": [
                {"symbol": "MSFT", "quantity": "1", "price_per_unit": "100"},
                {"symbol": "AAPL", "quantity": "2", "price_per_unit": "100"},
                {"symbol": "AMZN", "quantity": "1", "price_per_unit": "300"},
            ],
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    first_page = client.get(
        f"/api/v1/portfolio/{portfolio_id}/positions/search",
        params={"limit": 2, "offset": 0},
    )
    assert first_page.status_code == 200
    data = first_page.json()
    assert data["result_count"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["has_more"] is True
    assert [item["symbol"] for item in data["positions"]] == ["AAPL", "AMZN"]

    second_page = client.get(
        f"/api/v1/portfolio/{portfolio_id}/positions/search",
        params={"limit": 2, "offset": 2},
    )
    assert second_page.status_code == 200
    data = second_page.json()
    assert data["result_count"] == 3
    assert data["has_more"] is False
    assert [item["symbol"] for item in data["positions"]] == ["MSFT"]


def test_portfolio_position_search_rejects_invalid_pagination(client: TestClient):
    created = client.post(
        "/api/v1/portfolio",
        json={"name": "Invalid pagination", "positions": []},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        response = client.get(
            f"/api/v1/portfolio/{portfolio_id}/positions/search",
            params=params,
        )
        assert response.status_code == 422
