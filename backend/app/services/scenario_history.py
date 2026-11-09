from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScenarioExecution
from app.services.scenario_report import (
    ScenarioReportRequest,
    create_scenario_report,
)


def _json_safe(value):
    """Convert financial Decimal values into exact JSON strings."""
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    return value


def create_scenario_execution(
    db: Session,
    request: ScenarioReportRequest,
) -> dict:
    """Calculate and persist a new scenario execution."""
    report = create_scenario_report(request)

    inputs = _json_safe(
        request.model_dump(mode="python")
    )
    results = _json_safe({
        key: value
        for key, value in report.items()
        if key not in {"scenario_id", "input_fingerprint"}
    })

    execution = ScenarioExecution(
        scenario_id=report["scenario_id"],
        input_fingerprint=report["input_fingerprint"],
        inputs=inputs,
        results=results,
    )

    try:
        db.add(execution)
        db.commit()
        db.refresh(execution)
    except Exception:
        db.rollback()
        raise

    return {
        **report,
        "execution_id": execution.id,
        "created_at": execution.created_at,
    }


def get_scenario_execution(
    db: Session,
    execution_id: int,
) -> ScenarioExecution | None:
    """Retrieve one persisted scenario execution."""
    statement = select(ScenarioExecution).where(
        ScenarioExecution.id == execution_id
    )

    return db.scalar(statement)
