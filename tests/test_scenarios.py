"""Scenario application: which override groups reach the engine, and isolation between scenarios."""

from datetime import date
from decimal import Decimal

import pytest

from vuurtoren.domain import (
    Account,
    AccountKind,
    CashFlow,
    CashFlowKind,
    Household,
    Person,
    Scenario,
    ScenarioOverrides,
)
from vuurtoren.engine import Assumptions, PlanInput, Projection, project
from vuurtoren.scenarios import apply_scenario

START = date(2026, 1, 1)


def baseline_plan() -> PlanInput:
    """Build a minimal one-person, two-account plan for scenario tests."""
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=40)
    people = [Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))]
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(20000),
            return_assumption=0.0,
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(150000),
            cost_basis=Decimal(150000),
            return_assumption=0.06,
        ),
    ]
    cash_flows = [
        CashFlow(
            id=10,
            household_id=1,
            label="Salary",
            amount_monthly=Decimal(5000),
            kind=CashFlowKind.INCOME,
        ),
        CashFlow(
            id=11,
            household_id=1,
            label="Living",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.EXPENSE,
        ),
    ]
    return PlanInput(
        household=household,
        people=people,
        accounts=accounts,
        cash_flows=cash_flows,
        milestones=[],
        start=START,
        assumptions=Assumptions(),
    )


def _scenario(**overrides: object) -> Scenario:
    return Scenario(
        id=99,
        household_id=1,
        name="s",
        overrides=ScenarioOverrides(**overrides),  # ty: ignore[invalid-argument-type]
    )


def _project(plan: PlanInput, scenario: Scenario) -> Projection:
    applied, tax_overrides = apply_scenario(plan, scenario)
    return project(applied, tax_overrides=tax_overrides)


# --- the applied groups change the projection in the expected direction ---


def test_cash_flow_override_raises_expenses_and_lowers_net_worth() -> None:
    """A higher expense override lowers ending net worth versus baseline."""
    plan = baseline_plan()
    base = _project(plan, _scenario())
    scn = _scenario(cash_flows={11: {"amount_monthly": "4000"}})
    higher_expense = _project(plan, scn)
    assert higher_expense.net_worth[0, -1] < base.net_worth[0, -1]


def test_added_milestone_fires() -> None:
    """An added milestone executes and raises net worth versus baseline."""
    plan = baseline_plan()
    base = _project(plan, _scenario())
    scn = _scenario(
        added_milestones=[
            {
                "id": 500,
                "household_id": 1,
                "label": "Windfall",
                "on_date": "2027-06-01",
                "params": {"type": "lump_sum_in", "amount": "50000"},
            }
        ]
    )
    with_gift = _project(plan, scn)
    assert with_gift.net_worth[0, -1] > base.net_worth[0, -1]


def test_household_fiscal_partners_lowers_wealth_tax() -> None:
    """Enabling fiscal partners doubles the Box 3 allowance and lowers wealth tax paid."""
    plan = baseline_plan()
    base = _project(plan, _scenario())
    scn = _scenario(household={"fiscal_partners": True})
    partnered = _project(plan, scn)
    # Doubling the Box 3 allowance shrinks the taxable base, so less wealth tax is paid.
    assert partnered.tax_paid["investment_tax"].sum() < base.tax_paid["investment_tax"].sum()
    assert partnered.tax_paid["investment_tax"].sum() > 0


def test_assumptions_override_changes_the_fire_number() -> None:
    """A higher SWR override lowers the computed FIRE number."""
    plan = baseline_plan()
    base = _project(plan, _scenario())
    scn = _scenario(assumptions={"swr": Decimal("0.05")})
    higher_swr = _project(plan, scn)
    # fire_number = annual_expenses / swr, so a higher SWR lowers it.
    assert higher_swr.fire.fire_number < base.fire.fire_number
    assert higher_swr.fire.fire_number == pytest.approx(3000 * 12 / 0.05)


# --- the shared-mutable-default failure mode ---


def test_two_scenarios_do_not_leak_into_each_other() -> None:
    """Two scenarios applied to the same plan do not share overrides or mutate the plan."""
    plan = baseline_plan()
    a = _project(plan, _scenario(cash_flows={11: {"amount_monthly": "4000"}}))
    b = _project(plan, _scenario(cash_flows={11: {"amount_monthly": "2000"}}))
    assert a.net_worth[0, -1] < b.net_worth[0, -1]
    # The baseline rows are untouched: b must equal a plan built with only b's override.
    b_independent = _project(
        baseline_plan(), _scenario(cash_flows={11: {"amount_monthly": "2000"}})
    )
    assert b.net_worth[0, -1] == b_independent.net_worth[0, -1]
    # The baseline flow object itself was never mutated.
    assert plan.cash_flows[1].amount_monthly == Decimal(3000)


def test_scenario_then_baseline_returns_baseline_numbers() -> None:
    """Projecting the baseline after a scenario still returns the baseline's own numbers."""
    plan = baseline_plan()
    baseline_before = _project(plan, _scenario())
    _project(
        plan,
        _scenario(cash_flows={11: {"amount_monthly": "9000"}}, household={"fiscal_partners": True}),
    )
    baseline_after = _project(plan, _scenario())
    assert baseline_after.net_worth[0, -1] == baseline_before.net_worth[0, -1]


# --- only the tax group reaches the engine ---


def test_only_the_tax_group_is_handed_to_the_engine() -> None:
    """apply_scenario strips every override group but tax before it reaches the engine."""
    plan = baseline_plan()
    scn = _scenario(
        cash_flows={11: {"amount_monthly": "4000"}},
        household={"fiscal_partners": True},
        assumptions={"swr": Decimal("0.05")},
        tax={"NL": {2026: {"box3_rate": Decimal("0.40")}}},
    )
    _, tax_overrides = apply_scenario(plan, scn)
    assert tax_overrides == {"NL": {2026: {"box3_rate": Decimal("0.40")}}}


# --- the accounts group (the allocation and sensitivity blocker) ---


def test_account_override_raises_return_and_lifts_net_worth() -> None:
    """A higher per-account return override lifts ending net worth versus baseline."""
    plan = baseline_plan()
    base = _project(plan, _scenario())
    higher = _project(plan, _scenario(accounts={2: {"return_assumption": 0.08}}))
    assert higher.net_worth[0][-1] > base.net_worth[0][-1]


def test_account_override_reallocates_without_changing_total() -> None:
    """Moving value between two accounts leaves the starting net worth untouched.

    The allocation comparison rests on this: an 80/20-vs-60/40 question is the same
    money split differently, so month 0 must match and only the growth path diverge.
    """
    plan = baseline_plan()
    base = _project(plan, _scenario())
    shifted = _project(
        plan,
        _scenario(
            accounts={
                1: {"manual_value": Decimal(50000)},
                2: {"manual_value": Decimal(120000)},
            }
        ),
    )
    assert shifted.net_worth[0][0] == base.net_worth[0][0]
    assert shifted.net_worth[0][-1] != base.net_worth[0][-1]


def test_account_override_does_not_mutate_the_baseline_plan() -> None:
    """Applying an accounts override leaves the caller's plan and rows untouched."""
    plan = baseline_plan()
    apply_scenario(plan, _scenario(accounts={2: {"return_assumption": 0.08}}))
    assert plan.accounts[1].return_assumption == 0.06


def test_account_override_for_unknown_id_raises() -> None:
    """An override targeting an account id that does not exist raises."""
    plan = baseline_plan()
    with pytest.raises(ValueError, match="unknown id"):
        apply_scenario(plan, _scenario(accounts={999: {"return_assumption": 0.08}}))


def test_account_override_unknown_field_raises() -> None:
    """An override field name that does not exist on Account raises."""
    plan = baseline_plan()
    with pytest.raises(ValueError, match="unknown"):
        apply_scenario(plan, _scenario(accounts={2: {"retrun_assumption": 0.08}}))


# --- deferred groups are rejected loudly (a 4xx), not silently ignored ---


def test_deferred_milestone_patch_raises() -> None:
    """A milestone patch not yet supported by apply_scenario raises, not silently ignored."""
    plan = baseline_plan()
    with pytest.raises(ValueError, match="not supported"):
        apply_scenario(plan, _scenario(milestones={7: {"on_date": "2030-01-01"}}))


def test_unknown_override_field_raises() -> None:
    """An override field name that does not exist on the target raises."""
    plan = baseline_plan()
    with pytest.raises(ValueError, match="unknown"):
        apply_scenario(plan, _scenario(cash_flows={11: {"amoutn_monthly": "4000"}}))


def test_cash_flow_override_for_unknown_id_raises() -> None:
    """An override targeting a cash flow id that does not exist raises."""
    plan = baseline_plan()
    with pytest.raises(ValueError, match="unknown id"):
        apply_scenario(plan, _scenario(cash_flows={999: {"amount_monthly": "4000"}}))


def test_a_decimal_assumption_override_survives_a_json_float() -> None:
    """`usd_to_eur` arrives from JSON as a float and must not be read through one.

    `Decimal(0.86)` is 0.860000000000000031086244689504... — invariant #4's exact failure
    mode, on the rate that translates every US figure in the projection.
    """
    applied, _ = apply_scenario(baseline_plan(), _scenario(assumptions={"usd_to_eur": 0.86}))
    assert applied.assumptions.usd_to_eur == Decimal("0.86")


def test_a_scenario_saved_under_the_old_assumption_name_still_applies() -> None:
    """`aow_growth_months_per_decade` was renamed; stored scenarios keep the old key."""
    applied, _ = apply_scenario(
        baseline_plan(), _scenario(assumptions={"aow_growth_months_per_decade": 6})
    )
    assert applied.assumptions.state_pension_growth_months_per_decade == 6


def test_a_tax_country_override_checks_every_account_s_treatment() -> None:
    """Moving the household to AT by scenario leaves `nl.*` accounts Austria cannot tax.

    Only patched accounts used to be checked, so the move silently taxed nothing.
    """
    with pytest.raises(ValueError, match=r"nl\.box3_bank"):
        apply_scenario(baseline_plan(), _scenario(household={"tax_country": "AT"}))


def test_a_tax_country_override_with_retagged_accounts_applies() -> None:
    """The same move goes through once every account carries an Austrian treatment."""
    applied, _ = apply_scenario(
        baseline_plan(),
        _scenario(
            household={"tax_country": "AT"},
            accounts={1: {"tax_treatment": "at.bank"}, 2: {"tax_treatment": "at.investment"}},
        ),
    )
    assert applied.household.tax_country == "AT"


def test_a_tax_country_override_with_no_regime_raises() -> None:
    """Unchecked, the unknown country surfaced as a KeyError inside the projection."""
    with pytest.raises(ValueError, match="ZZ"):
        apply_scenario(baseline_plan(), _scenario(household={"tax_country": "ZZ"}))
