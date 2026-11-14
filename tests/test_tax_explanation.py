"""The explanation observes real engine assessments without changing their amounts."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from test_engine import NO_SWEEP, simple_plan
from vuurtoren.domain import Account, AccountKind, CashFlow, CashFlowKind, Person
from vuurtoren.engine import project
from vuurtoren.tax.nl.box1 import box1_steps, box1_tax_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for
from vuurtoren.tax.nl.explanation import NLTaxExplanation


@pytest.mark.parametrize("partners", [False, True])
@pytest.mark.parametrize("year", [2026, 2028])
def test_recording_keeps_engine_results_and_each_taxpayer(*, partners: bool, year: int) -> None:
    """Actual assessments survive the following hypothetical investment-drag calls."""
    plan = simple_plan(start=date(year, 7, 1), assumptions=NO_SWEEP)
    plan = replace(
        plan,
        household=plan.household.model_copy(update={"fiscal_partners": partners}),
        people=[*plan.people, Person(id=2, household_id=1, name="B", birth_date=date(1991, 1, 1))],
    )
    recorder = NLTaxExplanation(year)
    recorded, baseline = project(plan, regime=recorder), project(plan)
    np.testing.assert_array_equal(recorded.net_worth, baseline.net_worth)
    for key in baseline.tax_paid:
        np.testing.assert_array_equal(recorded.tax_paid[key], baseline.tax_paid[key])
    assert len(recorder.box3) == (1 if partners else 2)
    amount = sum(
        Decimal(step.value)
        for c in recorder.box3
        for step in c.steps
        if step.rule == "Box 3-belasting"
    )
    assert amount == Decimal(str(baseline.tax_paid["investment_tax"][0, 0]))
    for calculation in recorder.calculations:
        for step in calculation.steps:
            assert step.parameters
            assert all(
                p.source.startswith("https://") and p.verified_on for p in step.parameters.values()
            )


def test_pension_explanation_keeps_december_true_up() -> None:
    """An end-year salary and December sale appear in the owner's final payout tax."""
    plan = simple_plan(
        assumptions=replace(NO_SWEEP, cash_buffer_mode="fixed", cash_buffer_fixed=Decimal(5000))
    )
    pension = Account(
        id=3,
        household_id=1,
        owner_person_id=1,
        name="Pension",
        kind=AccountKind.PENSION,
        tax_treatment="nl.box1_pension",
        manual_value=Decimal(100000),
        liquid_from=date(2026, 1, 1),
    )
    plan = replace(
        plan,
        accounts=[plan.accounts[0], pension],
        cash_flows=[
            CashFlow(
                id=1,
                household_id=1,
                owner_person_id=1,
                label="Expenses",
                kind=CashFlowKind.EXPENSE,
                amount_monthly=Decimal(4000),
            ),
            CashFlow(
                id=2,
                household_id=1,
                owner_person_id=1,
                label="December income",
                inflation_linked=False,
                kind=CashFlowKind.INCOME,
                amount_monthly=Decimal(20000),
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 31),
            ),
        ],
    )
    recorder = NLTaxExplanation(2026)
    recorded = project(plan, regime=recorder)
    assert recorder.payouts
    final = recorder.payouts[1][-1].steps[0]
    assert Decimal(final.value) == Decimal(str(recorded.tax_paid["withdrawal_tax"][0, 0]))
    assert Decimal(recorder.payouts[1][0].steps[0].value) == Decimal(20000)
    baseline = project(plan)
    np.testing.assert_array_equal(recorded.net_worth, baseline.net_worth)


@pytest.mark.parametrize("share", [0.0, 0.5, 1.0])
def test_income_steps_reconstruct_the_shared_schedule(share: float) -> None:
    """Weighted age schedules preserve each floor and all three credit types."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    income = np.array([0.0, 10000.0, 50000.0, 100000.0])
    labour = income / 2
    steps = box1_steps(income, labour_income=labour, aow_share=share, cfg=cfg)
    total = np.zeros_like(income)
    for prefix, weight in (("below", 1 - share), ("aow", share)):
        if weight == 0:
            continue
        subtotal = sum(steps[f"{prefix}_bracket_{i}"] for i in (1, 2, 3))
        subtotal -= sum(steps[f"{prefix}_{credit}"] for credit in ("general", "labour", "elderly"))
        total += weight * np.maximum(subtotal, 0)
    # Reassociating the float64 additions may differ below one millionth of a cent.
    np.testing.assert_allclose(total, steps["tax"], rtol=1e-13, atol=1e-8, strict=True)
    np.testing.assert_array_equal(
        steps["tax"], box1_tax_array(income, labour_income=labour, aow_share=share, cfg=cfg)
    )
