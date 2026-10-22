from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_portfolio_valuation():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "price_per_unit": "200",
                },
                {
                    "symbol": "MSFT",
                    "quantity": "5",
                    "price_per_unit": "400",
                },
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["position_count"] == 2
    assert float(data["total_market_value"]) == 4000.0


def test_portfolio_rejects_zero_quantity():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "0",
                    "price_per_unit": "200",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_portfolio_rejects_empty_positions():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={"positions": []},
    )

    assert response.status_code == 422
