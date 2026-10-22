from fastapi import APIRouter

from app.services.stress import (
    StressRequest,
    calculate_stress,
)

router = APIRouter(prefix="/api/v1/scenarios", tags=["Scenarios"])


@router.post("/stress")
def stress_portfolio(request: StressRequest):
    return calculate_stress(request)
