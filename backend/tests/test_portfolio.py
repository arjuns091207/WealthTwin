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


def test_portfolio_valuation_supports_fractional_quantities():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "BOND-1",
                    "quantity": "2.5",
                    "price_per_unit": "10.25",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert float(response.json()["total_market_value"]) == 25.625


def test_portfolio_valuation_accepts_zero_price():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "ASSET-1",
                    "quantity": "10",
                    "price_per_unit": "0",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert float(response.json()["total_market_value"]) == 0.0


def test_portfolio_valuation_accepts_500_positions():
    positions = [
        {
            "symbol": f"ASSET-{index}",
            "quantity": "1",
            "price_per_unit": "2",
        }
        for index in range(500)
    ]

    response = client.post(
        "/api/v1/portfolio/valuation",
        json={"positions": positions},
    )

    assert response.status_code == 200
    assert response.json()["position_count"] == 500
    assert float(response.json()["total_market_value"]) == 1000.0


def test_portfolio_valuation_rejects_more_than_500_positions():
    positions = [
        {
            "symbol": f"ASSET-{index}",
            "quantity": "1",
            "price_per_unit": "2",
        }
        for index in range(501)
    ]

    response = client.post(
        "/api/v1/portfolio/valuation",
        json={"positions": positions},
    )

    assert response.status_code == 422


def test_portfolio_rejects_infinite_quantity():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "Infinity",
                    "price_per_unit": "100",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_portfolio_rejects_infinite_price():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "1",
                    "price_per_unit": "Infinity",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_portfolio_rejects_nan_price():
    response = client.post(
        "/api/v1/portfolio/valuation",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "1",
                    "price_per_unit": "NaN",
                }
            ]
        },
    )

    assert response.status_code == 422
