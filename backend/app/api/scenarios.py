from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.stress import (
    StressRequest,
    calculate_stress,
)
from app.services.scenario_report import ScenarioReportRequest
from app.services.scenario_history import (
    create_scenario_execution,
    get_scenario_execution,
)

router = APIRouter(prefix="/api/v1/scenarios", tags=["Scenarios"])


@router.post("/stress")
def stress_portfolio(request: StressRequest):
    return calculate_stress(request)


@router.post("/report")
def scenario_report(
    request: ScenarioReportRequest,
    db: Session = Depends(get_db),
):
    return create_scenario_execution(db, request)


@router.get("/executions/{execution_id}")
def scenario_execution(
    execution_id: int,
    db: Session = Depends(get_db),
):
    execution = get_scenario_execution(db, execution_id)

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Scenario execution not found",
        )

    return {
        "execution_id": execution.id,
        "scenario_id": execution.scenario_id,
        "input_fingerprint": execution.input_fingerprint,
        "inputs": execution.inputs,
        "results": execution.results,
        "created_at": execution.created_at,
    }