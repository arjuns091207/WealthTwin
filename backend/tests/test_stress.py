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


def test_full_loss_shock_reduces_position_value_to_zero():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "10",
                    "price_per_unit": "25",
                    "shock_percent": "-100",
                }
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["total_before"])) == Decimal("250")
    assert Decimal(str(data["total_after"])) == Decimal("0")
    assert Decimal(str(data["total_change"])) == Decimal("-250")


def test_mixed_shocks_reconcile_to_portfolio_change():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "10",
                    "price_per_unit": "100",
                    "shock_percent": "-20",
                },
                {
                    "symbol": "ASSET-B",
                    "quantity": "5",
                    "price_per_unit": "200",
                    "shock_percent": "10",
                },
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()

    position_changes = sum(
        (Decimal(str(position["change"])) for position in data["positions"]),
        Decimal("0"),
    )

    assert position_changes == Decimal(str(data["total_change"]))
    assert Decimal(str(data["total_before"])) == Decimal("2000")
    assert Decimal(str(data["total_after"])) == Decimal("1900")
    assert position_changes == Decimal("-100")


def test_zero_shock_preserves_portfolio_value():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "ASSET-A",
                    "quantity": "3",
                    "price_per_unit": "125.50",
                    "shock_percent": "0",
                }
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["total_before"])) == Decimal("376.50")
    assert Decimal(str(data["total_after"])) == Decimal("376.50")
    assert Decimal(str(data["total_change"])) == Decimal("0")



def test_loss_attribution_separates_losses_from_offsetting_gains():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "LOSER",
                    "quantity": "10",
                    "price_per_unit": "100",
                    "shock_percent": "-20",
                },
                {
                    "symbol": "WINNER",
                    "quantity": "5",
                    "price_per_unit": "100",
                    "shock_percent": "10",
                },
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    positions = {item["symbol"]: item for item in data["positions"]}

    assert Decimal(str(data["gross_losses"])) == Decimal("200")
    assert Decimal(str(data["total_gains"])) == Decimal("50")
    assert Decimal(str(data["total_change"])) == Decimal("-150")
    assert Decimal(str(positions["LOSER"]["loss_contribution_percent"])) == Decimal("100")
    assert Decimal(str(positions["WINNER"]["loss_contribution_percent"])) == Decimal("0")


def test_loss_contributions_sum_to_100_percent():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "LOSER-A",
                    "quantity": "1",
                    "price_per_unit": "100",
                    "shock_percent": "-10",
                },
                {
                    "symbol": "LOSER-B",
                    "quantity": "1",
                    "price_per_unit": "100",
                    "shock_percent": "-30",
                },
            ]
        },
    )

    assert response.status_code == 200
    positions = response.json()["positions"]
    contributions = sum(
        (Decimal(str(item["loss_contribution_percent"])) for item in positions),
        Decimal("0"),
    )

    assert contributions == Decimal("100")
    assert Decimal(str(positions[0]["loss_contribution_percent"])) == Decimal("25")
    assert Decimal(str(positions[1]["loss_contribution_percent"])) == Decimal("75")


def test_loss_attribution_is_zero_when_no_positions_lose_value():
    response = client.post(
        "/api/v1/scenarios/stress",
        json={
            "positions": [
                {
                    "symbol": "WINNER",
                    "quantity": "2",
                    "price_per_unit": "50",
                    "shock_percent": "10",
                },
                {
                    "symbol": "UNCHANGED",
                    "quantity": "1",
                    "price_per_unit": "100",
                    "shock_percent": "0",
                },
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert Decimal(str(data["gross_losses"])) == Decimal("0")
    assert Decimal(str(data["total_gains"])) == Decimal("10")
    assert all(
        Decimal(str(item["loss_contribution_percent"])) == Decimal("0")
        for item in data["positions"]
    )
