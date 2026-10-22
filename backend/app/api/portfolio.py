from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator


router = APIRouter(prefix="/api/v1/portfolio", tags=["Portfolio"])


class Position(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0)
    price_per_unit: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_finite_values(self):
        values = (self.quantity, self.price_per_unit)
        if not all(value.is_finite() for value in values):
            raise ValueError("Financial inputs must be finite")
        return self


class PortfolioValuationRequest(BaseModel):
    positions: list[Position] = Field(min_length=1, max_length=500)


@router.post("/valuation")
def calculate_portfolio_valuation(request: PortfolioValuationRequest):
    position_values = [
        {
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in request.positions
    ]

    total_market_value = sum(
        (position["market_value"] for position in position_values),
        Decimal("0"),
    )

    return {
        "position_count": len(position_values),
        "positions": position_values,
        "total_market_value": total_market_value,
    }
