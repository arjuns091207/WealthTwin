from fastapi.testclient import TestClient

from app.main import app
from app.services.scenario_report import (
    ScenarioReportRequest,
    create_scenario_report,
)

client = TestClient(app)


def sample_payload():
    return {
        "scenario_id": "market-crash-01",
        "positions": [
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
        ],
    }


def test_identical_scenario_inputs_produce_same_fingerprint():
    payload = sample_payload()

    first = create_scenario_report(
        ScenarioReportRequest(**payload)
    )
    second = create_scenario_report(
        ScenarioReportRequest(**payload)
    )

    assert first["input_fingerprint"] == second["input_fingerprint"]
    assert len(first["input_fingerprint"]) == 64


def test_decimal_formatting_does_not_change_fingerprint():
    first_payload = sample_payload()
    second_payload = sample_payload()

    first_payload["positions"][0]["quantity"] = "10.0"
    second_payload["positions"][0]["quantity"] = "10.000"

    first = create_scenario_report(
        ScenarioReportRequest(**first_payload)
    )
    second = create_scenario_report(
        ScenarioReportRequest(**second_payload)
    )

    assert first["input_fingerprint"] == second["input_fingerprint"]


def test_changed_shock_changes_fingerprint():
    first_payload = sample_payload()
    second_payload = sample_payload()
    second_payload["positions"][0]["shock_percent"] = "-30"

    first = create_scenario_report(
        ScenarioReportRequest(**first_payload)
    )
    second = create_scenario_report(
        ScenarioReportRequest(**second_payload)
    )

    assert first["input_fingerprint"] != second["input_fingerprint"]


def test_report_endpoint_returns_validated_scenario_results():
    response = client.post(
        "/api/v1/scenarios/report",
        json=sample_payload(),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["scenario_id"] == "market-crash-01"
    assert len(data["input_fingerprint"]) == 64
    assert data["total_before"] == 2000
    assert data["total_after"] == 1900
    assert data["total_change"] == -100


def test_report_endpoint_rejects_invalid_scenario_id():
    payload = sample_payload()
    payload["scenario_id"] = "../invalid id"

    response = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert response.status_code == 422

