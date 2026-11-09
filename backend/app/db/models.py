from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_portfolios_name_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=utc_now,
    server_default=text("now()"),
    nullable=False,
    )

    positions: Mapped[list["PortfolioPosition"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "symbol",
            name="uq_portfolio_positions_portfolio_symbol",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_portfolio_positions_quantity_positive",
        ),
        CheckConstraint(
            "price_per_unit >= 0",
            name="ck_portfolio_positions_price_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )
    price_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    portfolio: Mapped[Portfolio] = relationship(
        back_populates="positions",
    )


class ScenarioExecution(Base):
    __tablename__ = "scenario_executions"

    __table_args__ = (
        Index(
            "ix_scenario_executions_fingerprint",
            "input_fingerprint",
        ),
        Index(
            "ix_scenario_executions_scenario_id",
            "scenario_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    scenario_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    input_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    inputs: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    results: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("now()"),
        nullable=False,
    )
