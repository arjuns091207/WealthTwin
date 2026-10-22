from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.services.stress import StressPosition, StressRequest, calculate_stress


client = TestClient(app)


def test_stress_calculation():
    request = StressRequest(
        positions=[
            StressPosition(
                symbol="AAPL",
                quantity=Decimal("10"),
                price_per_unit=Decimal("200"),
                shock_percent=Decimal("-20"),
            ),
            StressPosition(
                symbol="MSFT",
                quantity=Decimal("5"),
                price_per_unit=Decimal("400"),
                shock_percent=Decimal("10"),
            ),
        ]
    )

    result = calculate_stress(request)

    assert result["total_before"] == Decimal("4000")
    assert result["total_after"] == Decimal("3800")
    assert result["total_change"] == Decimal("-200")
    assert sum(
        (item["change"] for item in result["positions"]),
        Decimal("0"),
    ) == result["total_change"]


def test_stress_api():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "price_per_unit": "200",
                    "shock_percent": "-20",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert Decimal(str(response.json()["total_after"])) == Decimal("1600")


def test_stress_rejects_below_minus_100_percent():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "price_per_unit": "200",
                    "shock_percent": "-120",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_stress_rejects_nonfinite_input():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "price_per_unit": "NaN",
                    "shock_percent": "10",
                }
            ]
        },
    )

    assert response.status_code == 422
