import hashlib
import json
from decimal import Decimal

from pydantic import BaseModel, Field

from app.services.stress import (
    StressPosition,
    StressRequest,
    calculate_stress,
)


class ScenarioReportRequest(BaseModel):
    scenario_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    positions: list[StressPosition] = Field(
        min_length=1,
        max_length=500,
    )


def _canonical_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def create_scenario_report(request: ScenarioReportRequest):
    canonical_input = {
        "scenario_id": request.scenario_id,
        "positions": [
            {
                "symbol": position.symbol,
                "quantity": _canonical_decimal(position.quantity),
                "price_per_unit": _canonical_decimal(
                    position.price_per_unit
                ),
                "shock_percent": _canonical_decimal(
                    position.shock_percent
                ),
            }
            for position in request.positions
        ],
    }

    canonical_json = json.dumps(
        canonical_input,
        sort_keys=True,
        separators=(",", ":"),
    )

    fingerprint = hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

    stress_request = StressRequest(positions=request.positions)
    results = calculate_stress(stress_request)

    return {
        "scenario_id": request.scenario_id,
        "input_fingerprint": fingerprint,
        **results,
    }
