from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_portfolio_valuation_matches_stress_baseline():
    positions = [
        {
            "symbol": "ALPHA",
            "quantity": "10",
            "price_per_unit": "100",
        },
        {
            "symbol": "BETA",
            "quantity": "5",
            "price_per_unit": "200",
        },
    ]

    valuation_response = client.post(
        "/api/v1/portfolio/valuation",
        json={"positions": positions},
    )
    stress_positions = [
        {**position, "shock_percent": "0"}
        for position in positions
    ]
    stress_response = client.post(
        "/api/v1/scenarios/stress",
        json={"positions": stress_positions},
    )

    assert valuation_response.status_code == 200
    assert stress_response.status_code == 200

    valuation = valuation_response.json()
    stress = stress_response.json()

    assert Decimal(str(valuation["total_market_value"])) == Decimal(
        str(stress["total_before"])
    )
    assert Decimal(str(valuation["total_market_value"])) == Decimal(
        str(stress["total_after"])
    )


def test_scenario_report_matches_stress_calculation():
    positions = [
        {
            "symbol": "ALPHA",
            "quantity": "10",
            "price_per_unit": "100",
            "shock_percent": "-20",
        },
        {
            "symbol": "BETA",
            "quantity": "5",
            "price_per_unit": "200",
            "shock_percent": "10",
        },
    ]

    stress_response = client.post(
        "/api/v1/scenarios/stress",
        json={"positions": positions},
    )
    report_response = client.post(
        "/api/v1/scenarios/report",
        json={
            "scenario_id": "integration-check",
            "positions": positions,
        },
    )

    assert stress_response.status_code == 200
    assert report_response.status_code == 200

    stress = stress_response.json()
    report = report_response.json()

    for field in (
        "total_before",
        "total_after",
        "total_change",
        "gross_losses",
        "total_gains",
    ):
        assert Decimal(str(report[field])) == Decimal(str(stress[field]))

    assert report["positions"] == stress["positions"]


def test_openapi_documents_all_core_endpoints():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/health" in paths
    assert "/api/v1/portfolio/valuation" in paths
    assert "/api/v1/scenarios/stress" in paths
    assert "/api/v1/scenarios/report" in paths
