"""Shared seeded PlanInput builder for the golden baseline.

Used by both tests/test_golden.py and scripts/regenerate_golden.py so the plan they
build stays byte-equivalent — a diff between them would make the golden drift test
meaningless.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from vuurtoren.db import create_all, make_engine
from vuurtoren.domain import BuyProperty, Milestone
from vuurtoren.engine import Assumptions, PlanInput
from vuurtoren.seed import load_household_spec, seed_household
from vuurtoren.tables import AccountRow, CashFlowRow, HouseholdRow, MilestoneRow, PersonRow

EXAMPLE_HOUSEHOLD = Path(__file__).parent.parent / "household.example.toml"
US_HOUSEHOLD = Path(__file__).parent.parent / "household.us.example.toml"
"""The second fixture, whose household has a US person. Kept apart from the first so the
original baseline can go on proving that a household without one is untouched."""


def build_seeded_plan(
    tmp_path: Path, spec_path: Path = EXAMPLE_HOUSEHOLD, *, buy_house: bool = True
) -> PlanInput:
    """Seed a household TOML into a fresh DB and load it back as a PlanInput.

    The defaults reproduce the original golden plan exactly — a change here that moved
    them would invalidate `baseline.json` silently. `buy_house` is off for the US fixture:
    a mortgage and a transfer tax would put most of that baseline's movement in Dutch
    housing arithmetic, where the overlay it exists to watch cannot reach.
    """
    engine = make_engine(tmp_path / f"golden-{spec_path.stem}.db")
    create_all(engine)
    with sessionmaker(engine)() as session:
        household_id = seed_household(session, load_household_spec(spec_path))
        household = session.get(HouseholdRow, household_id)
        assert household is not None
        # order_by(id) throughout: an unordered query leaves row order to the
        # query plan, and the engine's float summation and its choice of cash
        # account both read that order. The baseline has to be reproducible.
        people = [
            r.to_domain()
            for r in session.query(PersonRow)
            .filter_by(household_id=household_id)
            .order_by(PersonRow.id)
        ]
        accounts = [
            r.to_domain()
            for r in session.query(AccountRow)
            .filter_by(household_id=household_id)
            .order_by(AccountRow.id)
        ]
        return PlanInput(
            household=household.to_domain(),
            people=people,
            accounts=accounts,
            # The salary / living expenses / DCA trio now seeds from the example
            # TOML itself, so the DB rows ARE the golden flows.
            cash_flows=[
                r.to_domain()
                for r in session.query(CashFlowRow)
                .filter_by(household_id=household_id)
                .order_by(CashFlowRow.id)
            ],
            milestones=[
                r.to_domain()
                for r in session.query(MilestoneRow)
                .filter_by(household_id=household_id)
                .order_by(MilestoneRow.id)
            ]
            + (
                [
                    Milestone(
                        id=1,
                        household_id=household_id,
                        label="Buy house",
                        on_date=date(2028, 6, 1),
                        params=BuyProperty(
                            price=Decimal(360000),
                            mortgage=Decimal(340000),
                            annual_rate=Decimal("0.042"),
                            term_months=360,
                            buyer_person_id=people[0].id,
                        ),
                    ),
                ]
                if buy_house
                else []
            ),
            start=date(2026, 1, 1),
            assumptions=Assumptions(),
        )
