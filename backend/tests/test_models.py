from decimal import Decimal

from app.db.base import Base
from app.db.models import (
    Portfolio,
    PortfolioPosition,
    ScenarioExecution,
)


def test_portfolio_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "portfolios",
        "portfolio_positions",
        "scenario_executions",
    }


def test_portfolio_name_is_required_and_bounded():
    column = Portfolio.__table__.c.name
    assert column.nullable is False
    assert column.type.length == 100


def test_portfolio_creation_timestamp_has_database_default():
    column = Portfolio.__table__.c.created_at
    assert column.nullable is False
    assert column.server_default is not None


def test_position_uses_fixed_precision_numeric_columns():
    for name in ("quantity", "price_per_unit"):
        column = PortfolioPosition.__table__.c[name]
        assert column.nullable is False
        assert column.type.precision == 24
        assert column.type.scale == 8


def test_position_constraints_are_declared():
    constraints = {
        constraint.name
        for constraint in PortfolioPosition.__table__.constraints
    }

    assert "ck_portfolio_positions_quantity_positive" in constraints
    assert "ck_portfolio_positions_price_nonnegative" in constraints
    assert "uq_portfolio_positions_portfolio_symbol" in constraints


def test_position_references_portfolio_with_cascade_delete():
    column = PortfolioPosition.__table__.c.portfolio_id
    foreign_key = next(iter(column.foreign_keys))

    assert foreign_key.target_fullname == "portfolios.id"
    assert foreign_key.ondelete == "CASCADE"


def test_portfolio_relationship_connects_positions():
    portfolio = Portfolio(name="Long-term investments")
    position = PortfolioPosition(
        symbol="ABC",
        quantity=Decimal("2.5"),
        price_per_unit=Decimal("100.00"),
    )

    portfolio.positions.append(position)

    assert position.portfolio is portfolio
    assert position in portfolio.positions

def test_scenario_execution_stores_inputs_and_results():
    assert ScenarioExecution.__table__.c.inputs.type.__class__.__name__ == "JSON"
    assert ScenarioExecution.__table__.c.results.type.__class__.__name__ == "JSON"


def test_scenario_execution_fingerprint_is_indexed():
    indexes = {
        index.name
        for index in ScenarioExecution.__table__.indexes
    }

    assert "ix_scenario_executions_fingerprint" in indexes
    assert "ix_scenario_executions_scenario_id" in indexes


def test_scenario_execution_fingerprint_is_not_unique():
    column = ScenarioExecution.__table__.c.input_fingerprint

    assert column.unique is not True
