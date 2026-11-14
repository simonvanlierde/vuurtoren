"""The explanation observes real engine assessments without changing their amounts."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from test_engine import NO_SWEEP, simple_plan
from vuurtoren.domain import Account, AccountKind, CashFlow, CashFlowKind, Person
from vuurtoren.engine import project
from vuurtoren.tax.nl.box1 import box1_steps, box1_tax_array, net_housing_tax_effect_array
from vuurtoren.tax.nl.box3 import box3_tax_array
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


def test_housing_steps_preserve_inputs_and_the_calculated_adjustment() -> None:
    """The report exposes every housing input and the unrounded Hillen share."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    woz, interest = np.array([500000.0]), np.array([10000.0])
    steps: dict[str, np.ndarray] = {}
    adjustment = net_housing_tax_effect_array(interest, woz, year=2026, cfg=cfg, steps=steps)
    assert set(steps) == {"woz", "interest", "ewf", "hillen", "housing_adjustment"}
    np.testing.assert_array_equal(steps["woz"], woz)
    np.testing.assert_array_equal(steps["interest"], interest)
    # The sourced 2026 EWF is 0.35%; HRA is 37.56%. These are cent-exact outputs.
    np.testing.assert_array_equal(steps["ewf"], [1750.0])
    np.testing.assert_array_equal(steps["hillen"], [float(cfg.hillen_rate)])
    np.testing.assert_array_equal(steps["housing_adjustment"], adjustment)
    np.testing.assert_array_equal(adjustment, [3098.70])


def test_forfait_explanation_keeps_every_input_and_intermediate() -> None:
    """A report must retain the amounts and each separate forfaitair return."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    steps: dict[str, np.ndarray] = {}
    tax = box3_tax_array(
        np.array([100000.0]),
        np.array([200000.0]),
        np.array([20000.0]),
        None,
        year=2026,
        fiscal_partners=False,
        cfg=cfg,
        steps=steps,
    )
    # 2026 sourced rates: 1.28%, 6%, 2.7%; debt threshold 3,800; allowance 59,357.
    income = float(
        (Decimal("12842.6") * Decimal(224443) / Decimal(283800)).quantize(Decimal("0.01"))
    )
    expected = {
        "bank": 100000.0,
        "investments": 200000.0,
        "debt": 20000.0,
        "eligible_debt": 16200.0,
        "grondslag": 283800.0,
        "allowance": 59357.0,
        "bank_return": 1280.0,
        "investment_return": 12000.0,
        "debt_return": 437.4,
        "rendement": 12842.6,
        "aandeel": 224443 / 283800,
        "forfaitair_income": income,
        "taxable": income,
        "tax": round(income * 0.36, 2),
    }
    assert set(steps) == set(expected)
    for key, value in expected.items():
        # Float64 multiplication can differ below one millionth of a cent.
        np.testing.assert_allclose(
            steps[key], np.array([value]), rtol=1e-13, atol=1e-8, strict=True
        )
    np.testing.assert_array_equal(tax, steps["tax"])


@pytest.mark.parametrize(
    ("gain", "income", "used", "taxable", "due", "carry", "partners"),
    [
        (15000.0, 13200.0, 4000.0, 9200.0, 3312.0, 0.0, False),
        (-3000.0, -3000.0, 0.0, 0.0, 0.0, 6500.0, False),
        (5000.0, 1400.0, 1400.0, 0.0, 0.0, 2600.0, True),
    ],
)
def test_wwr_explanation_keeps_losses_and_each_intermediate(
    gain: float,
    income: float,
    used: float,
    taxable: float,
    due: float,
    carry: float,
    *,
    partners: bool,
) -> None:
    """Loss use and loss carry are separate outputs, including in a losing year."""
    cfg = defaults_for("NL", 2028, expect=NLTaxConfig)
    steps: dict[str, np.ndarray] = {}
    tax = box3_tax_array(
        np.zeros(1),
        np.zeros(1),
        np.zeros(1),
        np.array([gain]),
        year=2028,
        fiscal_partners=partners,
        cfg=cfg,
        loss_carry=np.array([4000.0]),
        steps=steps,
    )
    expected = {
        "actual_return": gain,
        "wwr_income": income,
        "loss_carry": 4000.0,
        "loss_used": used,
        "taxable": taxable,
        "tax": due,
        "next_carry": carry,
    }
    assert set(steps) == set(expected)
    for key, value in expected.items():
        np.testing.assert_array_equal(steps[key], [value])
    np.testing.assert_array_equal(tax, steps["tax"])


@pytest.mark.parametrize("bank", [0.0, 59357.0])
def test_explanation_shows_zero_share_below_or_at_the_wealth_allowance(bank: float) -> None:
    """A zero or exactly exempt base has no taxable share or return."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    steps: dict[str, np.ndarray] = {}
    tax = box3_tax_array(
        np.array([bank]),
        np.zeros(1),
        np.zeros(1),
        None,
        year=2026,
        fiscal_partners=False,
        cfg=cfg,
        steps=steps,
    )
    np.testing.assert_array_equal(steps["aandeel"], [0.0])
    np.testing.assert_array_equal(steps["forfaitair_income"], [0.0])
    np.testing.assert_array_equal(tax, [0.0])


@pytest.mark.parametrize("share", [0.0, 0.5, 1.0])
def test_income_steps_keep_exact_terms_with_reversed_thresholds(share: float) -> None:
    """Accepted overrides retain the engine's inverted clip bounds in each term."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    cfg = NLTaxConfig.model_validate({**cfg.model_dump(), "box1_bracket_1_to": Decimal(100000)})
    income = np.array([0.0, 50000.0, 120000.0])
    labour = np.zeros_like(income)
    steps = box1_steps(income, labour_income=labour, aow_share=share, cfg=cfg)
    total = np.zeros_like(income)
    for prefix, weight, rate in (
        ("below", 1 - share, cfg.box1_rate_1),
        ("aow", share, cfg.box1_rate_1 - cfg.aow_premium_rate),
    ):
        if weight == 0:
            continue
        expected = (
            np.minimum(income, 100000.0) * float(rate),
            np.full_like(income, float(cfg.box1_bracket_2_to) - 100000.0) * float(cfg.box1_rate_2),
            np.maximum(income - float(cfg.box1_bracket_2_to), 0.0) * float(cfg.box1_rate_3),
        )
        for number, value in enumerate(expected, 1):
            np.testing.assert_array_equal(steps[f"{prefix}_bracket_{number}"], value)
        subtotal = sum(expected) - sum(
            steps[f"{prefix}_{credit}"] for credit in ("general", "labour", "elderly")
        )
        total += weight * np.maximum(subtotal, 0.0)
    np.testing.assert_allclose(total, steps["tax"], rtol=1e-13, atol=1e-8)


@pytest.mark.parametrize("share", [0.0, 0.5, 1.0])
def test_income_steps_reconstruct_the_shared_schedule(share: float) -> None:
    """Weighted age schedules preserve each floor and all three credit types."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    income = np.array([0.0, 10000.0, 50000.0, 100000.0])
    labour = income / 2
    steps = box1_steps(income, labour_income=labour, aow_share=share, cfg=cfg)
    np.testing.assert_array_equal(steps["income"], income)
    np.testing.assert_array_equal(steps["labour_income"], labour)
    total = np.zeros_like(income)
    for prefix, weight in (("below", 1 - share), ("aow", share)):
        if weight == 0:
            continue
        np.testing.assert_array_equal(steps[f"{prefix}_share"], np.full_like(income, weight))
        subtotal = sum(steps[f"{prefix}_bracket_{i}"] for i in (1, 2, 3))
        subtotal -= sum(steps[f"{prefix}_{credit}"] for credit in ("general", "labour", "elderly"))
        total += weight * np.maximum(subtotal, 0)
    # Reassociating the float64 additions may differ below one millionth of a cent.
    np.testing.assert_allclose(total, steps["tax"], rtol=1e-13, atol=1e-8, strict=True)
    np.testing.assert_array_equal(
        steps["tax"], box1_tax_array(income, labour_income=labour, aow_share=share, cfg=cfg)
    )
