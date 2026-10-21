"""Database session plumbing and the lookups every route shares."""

from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from vuurtoren import domain
from vuurtoren.db import Base, default_db_path, make_engine, upgrade_to_head
from vuurtoren.engine import Assumptions, PlanInput
from vuurtoren.scenarios import apply_scenario
from vuurtoren.tables import (
    AccountRow,
    CashFlowRow,
    HouseholdRow,
    MilestoneRow,
    PersonRow,
    PricePointRow,
    ScenarioRow,
)
from vuurtoren.tax.config import check_tax_overrides

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine

    from vuurtoren.api.schemas import PlanRequestBase

# NOTE: one SQLite file, one writer, cached engine for the process lifetime — the
# "one service, one process" story. Tests override `get_session` entirely, so this
# default path is never touched by the test suite.


@lru_cache
def _engine() -> Engine:
    path = default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(path)
    # Migrating here rather than by hand: this is a single-user local service, so there
    # is no second process to race and nobody to run a deploy step. `lifespan` warms this
    # before the first request, which is what keeps the migration off the request path.
    upgrade_to_head(engine)
    return engine


def get_session() -> Iterator[Session]:
    """Yield a session on the process-wide engine, closed when the request ends."""
    with sessionmaker(bind=_engine())() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_or_404[RowT: Base](session: Session, row_cls: type[RowT], item_id: int) -> RowT:
    """Fetch one row by id, or answer 404."""
    row = session.get(row_cls, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{row_cls.__name__} {item_id} not found")
    return row


def household_rows[RowT: Base](session: Session, row_cls: type[RowT], hh_id: int) -> list[RowT]:
    """One household's rows of `row_cls`, in id order."""
    return (
        session.query(row_cls).filter_by(household_id=hh_id).order_by(row_cls.__table__.c.id).all()
    )


def household_or_404(session: Session, household_id: int | None) -> HouseholdRow:
    """Fetch the named household, or the sole one when `household_id` is None."""
    row = (
        session.get(HouseholdRow, household_id)
        if household_id is not None
        else session.query(HouseholdRow).order_by(HouseholdRow.id).first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no household found")
    return row


@contextmanager
def plan_errors_as_400() -> Iterator[None]:
    """Answer 400 for a plan or scenario the engine refuses to run."""
    try:
        yield
    except (ValueError, NotImplementedError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def planned(session: Session, body: PlanRequestBase) -> tuple[PlanInput, domain.TaxOverrides]:
    """The plan a request describes, with its scenario applied, plus the tax overrides.

    Hand both to `project` (`tax_overrides=`). A scenario that cannot be applied answers
    400 here; wrap the projection itself in `plan_errors_as_400` for the same treatment.
    """
    plan, scenario = _assemble_plan(session, body)
    if scenario is None:
        return plan, {}
    with plan_errors_as_400():
        # Live overrides are never saved, and a stored scenario may predate the check.
        check_tax_overrides(scenario.overrides.tax)
        return apply_scenario(plan, scenario)


def _assemble_plan(
    session: Session,
    body: PlanRequestBase,
) -> tuple[PlanInput, domain.Scenario | None]:
    """Build a PlanInput and resolve the (unapplied) scenario the request carries."""
    household_row = household_or_404(session, body.household_id)
    hh_id = household_row.id

    scenario = None
    if body.scenario_id is not None:
        scenario = get_or_404(session, ScenarioRow, body.scenario_id).to_domain()
    if body.overrides is not None:
        if scenario is not None:
            raise HTTPException(
                status_code=400, detail="pass either scenario_id or overrides, not both"
            )
        scenario = domain.Scenario(
            id=0, household_id=hh_id, name="live preview", overrides=body.overrides
        )

    plan = PlanInput(
        household=household_row.to_domain(),
        people=[r.to_domain() for r in household_rows(session, PersonRow, hh_id)],
        accounts=_accounts_at_latest_price(session, hh_id),
        cash_flows=[r.to_domain() for r in household_rows(session, CashFlowRow, hh_id)],
        milestones=[r.to_domain() for r in household_rows(session, MilestoneRow, hh_id)],
        start=body.start,
        assumptions=Assumptions(**body.assumptions.model_dump()),
    )
    return plan, scenario


def _accounts_at_latest_price(session: Session, hh_id: int) -> list[domain.Account]:
    """The household's accounts, each opening on its latest price point when it has one.

    The same rule the Accounts view shows: a fetched or manually entered price beats the
    stored `manual_value`, so the plan opens on the balance the user last saw.
    """
    rows = household_rows(session, AccountRow, hh_id)
    latest = {
        p.account_id: p.value_eur
        for p in session.query(PricePointRow)
        .filter(PricePointRow.account_id.in_([r.id for r in rows]))
        .order_by(PricePointRow.date)
    }
    return [
        a.model_copy(update={"manual_value": latest[a.id]}) if a.id in latest else a
        for a in (r.to_domain() for r in rows)
    ]
