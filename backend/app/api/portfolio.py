from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import Portfolio, PortfolioPosition
from app.db.session import get_db

from datetime import datetime


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


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    positions: list[Position] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Portfolio name must not be blank")
        return self


class PortfolioPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    quantity: Decimal
    price_per_unit: Decimal


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    positions: list[PortfolioPositionRead]


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    request: PortfolioCreate,
    db: Session = Depends(get_db),
):
    portfolio = Portfolio(name=request.name)
    portfolio.positions = [
        PortfolioPosition(
            symbol=position.symbol,
            quantity=position.quantity,
            price_per_unit=position.price_per_unit,
        )
        for position in request.positions
    ]

    db.add(portfolio)
    try:
        db.commit()
        db.refresh(portfolio)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Portfolio contains duplicate symbols",
        ) from exc

    return portfolio


@router.get("", response_model=list[PortfolioRead])
def list_portfolios(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return portfolios ordered by creation time, newest first."""
    statement = (
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .order_by(Portfolio.created_at.desc(), Portfolio.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get("/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    statement = (
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    )
    portfolio = db.scalars(statement).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Delete a portfolio and its associated positions."""
    portfolio = db.get(Portfolio, portfolio_id)

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    db.delete(portfolio)
    db.commit()


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
