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

class PortfolioRebalanceRequest(BaseModel):
    target_allocations: dict[str, Decimal] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_target_allocations(self):
        if any(not value.is_finite() or value < 0 for value in self.target_allocations.values()):
            raise ValueError("Target allocations must be finite and non-negative")

        if any(not symbol.strip() for symbol in self.target_allocations):
            raise ValueError("Symbols must not be blank")

        if len({symbol.strip().upper() for symbol in self.target_allocations}) != len(self.target_allocations):
            raise ValueError("Duplicate symbols are not allowed")

        if sum(self.target_allocations.values(), Decimal("0")) != Decimal("100"):
            raise ValueError("Target allocations must sum to exactly 100")

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


class PortfolioUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

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


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(
    portfolio_id: int,
    request: PortfolioUpdate,
    db: Session = Depends(get_db),
):
    """Rename a saved portfolio without changing its positions."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    portfolio.name = request.name
    db.commit()
    db.refresh(portfolio)

    return portfolio


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


@router.post(
    "/{portfolio_id}/positions",
    response_model=PortfolioRead,
    status_code=status.HTTP_200_OK,
)
def add_portfolio_position(
    portfolio_id: int,
    request: Position,
    db: Session = Depends(get_db),
):
    """Add a holding to an existing portfolio."""
    portfolio = db.get(Portfolio, portfolio_id)

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    position = PortfolioPosition(
        portfolio_id=portfolio_id,
        symbol=request.symbol,
        quantity=request.quantity,
        price_per_unit=request.price_per_unit,
    )
    db.add(position)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Portfolio already contains this symbol",
        ) from exc

    statement = (
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    )
    return db.scalars(statement).first()


@router.delete("/{portfolio_id}/positions/{position_id}", response_model=PortfolioRead)
def remove_portfolio_position(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
):
    """Remove one holding while keeping the portfolio."""
    portfolio = db.get(Portfolio, portfolio_id)

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    position = db.get(PortfolioPosition, position_id)

    if position is None or position.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Position not found in this portfolio",
        )

    db.delete(position)
    db.commit()

    statement = (
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    )
    return db.scalars(statement).first()


@router.get("/{portfolio_id}/valuation")
def value_saved_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Calculate market values for a persisted portfolio."""
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

    position_values = [
        {
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    total_market_value = sum(
        (item["market_value"] for item in position_values),
        Decimal("0"),
    )

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "position_count": len(position_values),
        "positions": position_values,
        "total_market_value": total_market_value,
    }


@router.get("/{portfolio_id}/allocation")
def get_portfolio_allocation(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Calculate each holding's percentage of portfolio market value."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    position_values = [
        {
            "position_id": position.id,
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    total_market_value = sum(
        (item["market_value"] for item in position_values),
        Decimal("0"),
    )

    for item in position_values:
        item["allocation_pct"] = (
            item["market_value"] / total_market_value * Decimal("100")
            if total_market_value > 0
            else Decimal("0")
        )

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "positions": position_values,
        "total_market_value": total_market_value,
    }



@router.get("/{portfolio_id}/allocation-bands")
def get_portfolio_allocation_bands(
    portfolio_id: int,
    dominant_threshold_pct: Decimal = Query(default=Decimal("20"), gt=0, le=100),
    medium_threshold_pct: Decimal = Query(default=Decimal("5"), ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Classify portfolio holdings by their percentage of total market value."""
    if medium_threshold_pct >= dominant_threshold_pct:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="medium_threshold_pct must be less than dominant_threshold_pct",
        )

    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    positions = [
        {
            "position_id": position.id,
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    total_market_value = sum(
        (position["market_value"] for position in positions),
        Decimal("0"),
    )

    bands = {"dominant": [], "medium": [], "small": []}

    for position in positions:
        allocation_pct = (
            position["market_value"] / total_market_value * Decimal("100")
            if total_market_value > 0
            else Decimal("0")
        )
        position["allocation_pct"] = allocation_pct

        if allocation_pct >= dominant_threshold_pct:
            band = "dominant"
        elif allocation_pct >= medium_threshold_pct:
            band = "medium"
        else:
            band = "small"

        position["band"] = band
        bands[band].append(position)

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "total_market_value": total_market_value,
        "thresholds": {
            "dominant_threshold_pct": dominant_threshold_pct,
            "medium_threshold_pct": medium_threshold_pct,
        },
        "bands": bands,
    }

@router.post("/{portfolio_id}/rebalance")
def rebalance_portfolio(
    portfolio_id: int,
    request: PortfolioRebalanceRequest,
    db: Session = Depends(get_db),
):
    """Calculate value-based trades needed to reach target allocations."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    targets = {
        symbol.strip().upper(): allocation
        for symbol, allocation in request.target_allocations.items()
    }

    positions_by_symbol = {
        position.symbol.upper(): position
        for position in portfolio.positions
    }

    unknown_symbols = sorted(set(targets) - set(positions_by_symbol))
    if unknown_symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Target symbols not in portfolio: {', '.join(unknown_symbols)}",
        )

    if set(targets) != set(positions_by_symbol):
        missing_symbols = sorted(set(positions_by_symbol) - set(targets))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing target allocations for: {', '.join(missing_symbols)}",
        )

    values = {
        symbol: position.quantity * position.price_per_unit
        for symbol, position in positions_by_symbol.items()
    }
    total_value = sum(values.values(), Decimal("0"))

    if total_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot rebalance a portfolio with zero market value",
        )

    recommendations = []
    for symbol, position in positions_by_symbol.items():
        current_value = values[symbol]
        current_weight = current_value / total_value * Decimal("100")
        target_weight = targets[symbol]
        target_value = total_value * target_weight / Decimal("100")
        trade_value = target_value - current_value

        recommendations.append(
            {
                "symbol": symbol,
                "current_market_value": current_value,
                "current_allocation_pct": current_weight,
                "target_allocation_pct": target_weight,
                "target_market_value": target_value,
                "trade_value": trade_value,
                "action": (
                    "buy" if trade_value > 0
                    else "sell" if trade_value < 0
                    else "hold"
                ),
            }
        )

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "total_market_value": total_value,
        "recommendations": sorted(
            recommendations,
            key=lambda item: item["symbol"],
        ),
        "note": (
            "Value-based estimates only; excludes taxes, transaction costs, "
            "market movements, and fractional-share restrictions."
        ),
    }


@router.get("/compare/{first_portfolio_id}/{second_portfolio_id}")
def compare_portfolios(
    first_portfolio_id: int,
    second_portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Compare valuation and diversification metrics for two portfolios."""
    if first_portfolio_id == second_portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose two different portfolios to compare",
        )

    portfolio_ids = [first_portfolio_id, second_portfolio_id]
    portfolios = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id.in_(portfolio_ids))
    ).all()

    portfolio_by_id = {portfolio.id: portfolio for portfolio in portfolios}

    missing_ids = [
        portfolio_id
        for portfolio_id in portfolio_ids
        if portfolio_id not in portfolio_by_id
    ]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio not found: {missing_ids[0]}",
        )

    def calculate_metrics(portfolio):
        values = [
            position.quantity * position.price_per_unit
            for position in portfolio.positions
        ]
        total = sum(values, Decimal("0"))
        hhi = Decimal("0")

        if total > 0:
            hhi = sum(
                (
                    (value / total) * (value / total)
                    for value in values
                ),
                Decimal("0"),
            )

        return {
            "portfolio_id": portfolio.id,
            "portfolio_name": portfolio.name,
            "position_count": len(values),
            "total_market_value": total,
            "herfindahl_hirschman_index": hhi,
            "effective_number_of_positions": (
                Decimal("1") / hhi if hhi > 0 else Decimal("0")
            ),
        }

    first = calculate_metrics(portfolio_by_id[first_portfolio_id])
    second = calculate_metrics(portfolio_by_id[second_portfolio_id])

    return {
        "first_portfolio": first,
        "second_portfolio": second,
        "market_value_difference": (
            first["total_market_value"] - second["total_market_value"]
        ),
    }


@router.get("/{portfolio_id}/analytics")
def get_portfolio_analytics(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Return combined valuation, concentration, and diversification metrics."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    positions = [
        {
            "position_id": position.id,
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    positions.sort(key=lambda item: item["market_value"], reverse=True)

    total_market_value = sum(
        (item["market_value"] for item in positions),
        Decimal("0"),
    )

    weights = []
    if total_market_value > 0:
        weights = [
            item["market_value"] / total_market_value
            for item in positions
        ]

    hhi = sum(
        (weight * weight for weight in weights),
        Decimal("0"),
    )
    effective_positions = Decimal("1") / hhi if hhi > 0 else Decimal("0")

    largest_position = None
    if positions:
        largest = positions[0]
        largest_position = {
            **largest,
            "allocation_pct": (
                largest["market_value"] / total_market_value * Decimal("100")
                if total_market_value > 0
                else Decimal("0")
            ),
        }

    top_three_value = sum(
        (item["market_value"] for item in positions[:3]),
        Decimal("0"),
    )
    top_three_allocation_pct = (
        top_three_value / total_market_value * Decimal("100")
        if total_market_value > 0
        else Decimal("0")
    )

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "position_count": len(positions),
        "total_market_value": total_market_value,
        "largest_position": largest_position,
        "largest_allocation_pct": (
            largest_position["allocation_pct"]
            if largest_position is not None
            else Decimal("0")
        ),
        "top_three_allocation_pct": top_three_allocation_pct,
        "herfindahl_hirschman_index": hhi,
        "effective_number_of_positions": effective_positions,
    }


@router.get("/{portfolio_id}/diversification")
def get_portfolio_diversification(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Calculate weight-based portfolio concentration and diversification."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    values = [
        position.quantity * position.price_per_unit
        for position in portfolio.positions
    ]
    total_market_value = sum(values, Decimal("0"))

    hhi = Decimal("0")
    effective_number_of_positions = Decimal("0")

    if total_market_value > 0:
        weights = [
            value / total_market_value
            for value in values
        ]
        hhi = sum(
            (weight * weight for weight in weights),
            Decimal("0"),
        )
        if hhi > 0:
            effective_number_of_positions = Decimal("1") / hhi

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "position_count": len(values),
        "total_market_value": total_market_value,
        "herfindahl_hirschman_index": hhi,
        "effective_number_of_positions": effective_number_of_positions,
    }


@router.get("/{portfolio_id}/risk")
def get_portfolio_risk(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Return portfolio concentration metrics based on position market values."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    values = [
        {
            "position_id": position.id,
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    values.sort(key=lambda item: item["market_value"], reverse=True)

    total_market_value = sum(
        (item["market_value"] for item in values),
        Decimal("0"),
    )

    largest_position = None
    largest_allocation_pct = Decimal("0")
    top_three_allocation_pct = Decimal("0")

    if total_market_value > 0:
        top_three_value = sum(
            (item["market_value"] for item in values[:3]),
            Decimal("0"),
        )
        top_three_allocation_pct = (
            top_three_value / total_market_value * Decimal("100")
        )

        if values:
            largest = values[0]
            largest_allocation_pct = (
                largest["market_value"]
                / total_market_value
                * Decimal("100")
            )
            largest_position = {
                **largest,
                "allocation_pct": largest_allocation_pct,
            }

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "position_count": len(values),
        "total_market_value": total_market_value,
        "largest_position": largest_position,
        "largest_allocation_pct": largest_allocation_pct,
        "top_three_allocation_pct": top_three_allocation_pct,
    }


@router.get("/{portfolio_id}/summary")
def get_portfolio_summary(
    portfolio_id: int,
    db: Session = Depends(get_db),
):
    """Return concise valuation and concentration metrics."""
    portfolio = db.scalars(
        select(Portfolio)
        .options(selectinload(Portfolio.positions))
        .where(Portfolio.id == portfolio_id)
    ).first()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    values = [
        {
            "position_id": position.id,
            "symbol": position.symbol,
            "market_value": position.quantity * position.price_per_unit,
        }
        for position in portfolio.positions
    ]

    total_market_value = sum(
        (item["market_value"] for item in values),
        Decimal("0"),
    )

    largest_position = None
    if values:
        largest = max(values, key=lambda item: item["market_value"])
        largest_position = {
            **largest,
            "allocation_pct": (
                largest["market_value"] / total_market_value * Decimal("100")
                if total_market_value > 0
                else Decimal("0")
            ),
        }

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "position_count": len(values),
        "total_market_value": total_market_value,
        "largest_position": largest_position,
    }


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
