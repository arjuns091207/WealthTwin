from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.db import models
from app.main import app
from app.services.scenario_report import (
    ScenarioReportRequest,
    create_scenario_report,
)


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

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


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


def test_report_endpoint_returns_validated_scenario_results(
    client: TestClient,
):
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
    assert data["execution_id"] is not None
    assert data["created_at"] is not None


def test_report_endpoint_rejects_invalid_scenario_id(
    client: TestClient,
):
    payload = sample_payload()
    payload["scenario_id"] = "../invalid id"

    response = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert response.status_code == 422


def test_changed_scenario_id_changes_fingerprint():
    first_payload = sample_payload()
    second_payload = sample_payload()
    second_payload["scenario_id"] = "market-crash-02"

    first = create_scenario_report(
        ScenarioReportRequest(**first_payload)
    )
    second = create_scenario_report(
        ScenarioReportRequest(**second_payload)
    )

    assert first["input_fingerprint"] != second["input_fingerprint"]


def test_reordering_positions_changes_fingerprint():
    first_payload = sample_payload()
    second_payload = sample_payload()
    second_payload["positions"].reverse()

    first = create_scenario_report(
        ScenarioReportRequest(**first_payload)
    )
    second = create_scenario_report(
        ScenarioReportRequest(**second_payload)
    )

    assert first["input_fingerprint"] != second["input_fingerprint"]


def test_report_endpoint_rejects_empty_positions(
    client: TestClient,
):
    payload = sample_payload()
    payload["positions"] = []

    response = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_more_than_500_positions(
    client: TestClient,
):
    payload = sample_payload()
    payload["positions"] = [payload["positions"][0]] * 501

    response = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_nonfinite_financial_input(
    client: TestClient,
):
    payload = sample_payload()
    payload["positions"][0]["quantity"] = "NaN"

    response = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert response.status_code == 422

def test_scenario_execution_is_persisted_and_retrievable(
    client: TestClient,
):
    response = client.post(
        "/api/v1/scenarios/report",
        json=sample_payload(),
    )

    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    retrieved = client.get(
        f"/api/v1/scenarios/executions/{execution_id}"
    )

    assert retrieved.status_code == 200

    data = retrieved.json()
    assert data["execution_id"] == execution_id
    assert data["scenario_id"] == "market-crash-01"
    assert len(data["input_fingerprint"]) == 64
    assert data["inputs"]["positions"][0]["quantity"] == "10"
    assert data["results"]["total_before"] == "2000"


def test_identical_executions_create_separate_history_records(
    client: TestClient,
):
    payload = sample_payload()

    first = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )
    second = client.post(
        "/api/v1/scenarios/report",
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_data = first.json()
    second_data = second.json()

    assert (
        first_data["input_fingerprint"]
        == second_data["input_fingerprint"]
    )
    assert first_data["execution_id"] != second_data["execution_id"]


def test_unknown_scenario_execution_returns_404(
    client: TestClient,
):
    response = client.get(
        "/api/v1/scenarios/executions/999999"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Scenario execution not found"