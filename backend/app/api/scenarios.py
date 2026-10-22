from fastapi import APIRouter

from app.services.stress import (
    StressRequest,
    calculate_stress,
)
from app.services.scenario_report import (
    ScenarioReportRequest,
    create_scenario_report,
)

router = APIRouter(prefix="/api/v1/scenarios", tags=["Scenarios"])


@router.post("/stress")
def stress_portfolio(request: StressRequest):
    return calculate_stress(request)


@router.post("/report")
def scenario_report(request: ScenarioReportRequest):
    return create_scenario_report(request)
