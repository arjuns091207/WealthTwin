from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class StressPosition(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0)
    price_per_unit: Decimal = Field(ge=0)
    shock_percent: Decimal = Field(ge=-100)

    @model_validator(mode="after")
    def validate_finite_values(self):
        values = (
            self.quantity,
            self.price_per_unit,
            self.shock_percent,
        )
        if not all(value.is_finite() for value in values):
            raise ValueError("Financial inputs must be finite")
        return self


class StressRequest(BaseModel):
    positions: list[StressPosition] = Field(min_length=1, max_length=500)


def calculate_stress(request: StressRequest):
    results = []
    total_before = Decimal("0")
    total_after = Decimal("0")

    for position in request.positions:
        before = position.quantity * position.price_per_unit
        after = before * (
            Decimal("1") + position.shock_percent / Decimal("100")
        )
        change = after - before

        results.append({
            "symbol": position.symbol,
            "value_before": before,
            "value_after": after,
            "change": change,
        })

        total_before += before
        total_after += after

    return {
        "positions": results,
        "total_before": total_before,
        "total_after": total_after,
        "total_change": total_after - total_before,
    }
