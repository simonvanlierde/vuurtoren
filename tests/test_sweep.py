"""Unit tests for the sweep mechanics, with no engine and no plan.

`sweep.py` is pure maths over arrays, so every case here constructs its balances
directly. Engine-level behaviour is tested in test_engine.py.
"""

from datetime import date

import numpy as np
import pytest

from vuurtoren.domain import Account, AccountKind
from vuurtoren.sweep import apply_sweep, sellable_accounts

WHEN = date(2030, 1, 1)


def acct(
    account_id: int,
    kind: AccountKind = AccountKind.EQUITY,
    *,
    vol: float = 0.0,
    liquid_from: date | None = None,
) -> Account:
    """Build a minimal Account for sweep tests."""
    return Account(
        id=account_id,
        household_id=1,
        name=f"a{account_id}",
        kind=kind,
        tax_treatment="nl.box3_investment",
        volatility_assumption=vol,
        liquid_from=liquid_from,
    )


def arr(*values: float) -> np.ndarray:
    """Build a float64 numpy array of per-run balances."""
    return np.array(values, dtype=float)


# --- eligibility ---


def test_only_equity_bond_and_pension_are_sellable() -> None:
    """Cash and debt accounts are excluded from the sellable set."""
    accounts = [
        acct(1, AccountKind.CASH),
        acct(2, AccountKind.EQUITY),
        acct(3, AccountKind.BOND),
        acct(4, AccountKind.REAL_ESTATE),
        acct(5, AccountKind.DEBT),
    ]
    assert [a.id for a in sellable_accounts(accounts, WHEN, "pro_rata")] == [2, 3]


def test_a_locked_pension_is_not_sellable_before_liquid_from() -> None:
    """The classic bug in this class of tool. Both sides asserted."""
    locked = acct(1, AccountKind.PENSION, liquid_from=date(2030, 2, 1))
    assert sellable_accounts([locked], date(2030, 1, 1), "pro_rata") == []
    assert [a.id for a in sellable_accounts([locked], date(2030, 2, 1), "pro_rata")] == [1]


def test_buy_targets_default_to_the_sources_but_can_be_narrowed() -> None:
    """The two directions are not symmetric.

    Capital taxed on the way out is sellable without being a sensible destination for
    surplus cash.
    """
    balances = {0: arr(50000.0), 1: arr(10000.0), 2: arr(10000.0)}
    sources = [acct(1), acct(2)]
    flow = apply_sweep(
        balances,
        0,
        sources,
        buy_targets=[acct(2)],
        target=10000.0,
        deadband=1.5,
        pro_rata=True,
    )
    # Threshold 15000, so 35000 is invested — all of it into account 2.
    assert flow[1] == pytest.approx(0.0)
    assert flow[2] == pytest.approx(35000.0)
    assert balances[0] == pytest.approx(15000.0)


def test_an_empty_buy_target_list_leaves_the_surplus_in_cash() -> None:
    """An empty buy_targets list leaves surplus cash uninvested rather than erroring."""
    balances = {0: arr(50000.0), 1: arr(10000.0)}
    apply_sweep(balances, 0, [acct(1)], buy_targets=[], target=10000.0, deadband=1.5, pro_rata=True)
    assert balances[0] == pytest.approx(50000.0)
    assert balances[1] == pytest.approx(10000.0)


def test_liquid_from_still_gates_an_ordinary_holding() -> None:
    """The lock is honoured for every kind, not only pensions."""
    locked = acct(1, AccountKind.EQUITY, liquid_from=date(2030, 2, 1))
    assert sellable_accounts([locked], date(2030, 1, 1), "pro_rata") == []
    assert [a.id for a in sellable_accounts([locked], date(2030, 2, 1), "pro_rata")] == [1]


def test_an_account_with_no_liquid_from_is_sellable() -> None:
    """`liquid_from = None` means liquid now, matching _fire_metrics."""
    assert [a.id for a in sellable_accounts([acct(1)], WHEN, "pro_rata")] == [1]


# --- ordering ---


def test_safest_first_sorts_ascending_by_volatility() -> None:
    """`safest_first` orders sellable accounts from lowest to highest volatility."""
    accounts = [acct(1, vol=0.18), acct(2, vol=0.03), acct(3, vol=0.09)]
    assert [a.id for a in sellable_accounts(accounts, WHEN, "safest_first")] == [2, 3, 1]


def test_riskiest_first_is_the_reverse() -> None:
    """`riskiest_first` orders sellable accounts from highest to lowest volatility."""
    accounts = [acct(1, vol=0.18), acct(2, vol=0.03), acct(3, vol=0.09)]
    assert [a.id for a in sellable_accounts(accounts, WHEN, "riskiest_first")] == [1, 3, 2]


def test_equal_volatility_ties_break_on_id_not_list_order() -> None:
    """`plan.accounts` arrives from an unordered query.

    Two accounts at equal volatility must not sweep differently because a query
    returned them swapped — the same hazard that makes engine.py pick min(cash_ids).
    """
    a, b = acct(7, vol=0.1), acct(3, vol=0.1)
    assert [x.id for x in sellable_accounts([a, b], WHEN, "safest_first")] == [3, 7]
    assert [x.id for x in sellable_accounts([b, a], WHEN, "safest_first")] == [3, 7]


def test_the_id_tie_break_runs_the_same_way_under_both_priority_orders() -> None:
    """Reversing the sorted list would flip the tie-break too.

    So two equal-volatility accounts would drain in opposite order under the two modes
    for no intended reason. Only the volatility ranking may differ between them.
    """
    accounts = [acct(7, vol=0.1), acct(3, vol=0.1), acct(5, vol=0.3)]
    assert [x.id for x in sellable_accounts(accounts, WHEN, "safest_first")] == [3, 7, 5]
    assert [x.id for x in sellable_accounts(accounts, WHEN, "riskiest_first")] == [5, 3, 7]


# --- selling ---


def test_a_deficit_is_refilled_pro_rata() -> None:
    """A cash deficit is refilled by selling from every source in proportion to its balance."""
    balances = {0: arr(0.0), 1: arr(80000.0), 2: arr(20000.0)}
    sources = [acct(1), acct(2)]
    flow = apply_sweep(balances, 0, sources, target=10000.0, deadband=1.5, pro_rata=True)
    assert balances[0] == pytest.approx(10000.0)
    assert balances[1] == pytest.approx(72000.0)
    assert balances[2] == pytest.approx(18000.0)
    assert flow[1] == pytest.approx(-8000.0)
    assert flow[2] == pytest.approx(-2000.0)


def test_pro_rata_preserves_the_allocation_ratio() -> None:
    """Selling pro rata across sources leaves their relative balances unchanged."""
    balances = {0: arr(0.0), 1: arr(75000.0), 2: arr(25000.0)}
    apply_sweep(balances, 0, [acct(1), acct(2)], target=40000.0, deadband=1.5, pro_rata=True)
    assert balances[1][0] / balances[2][0] == pytest.approx(3.0)


def test_a_priority_order_drains_the_first_account_before_the_second() -> None:
    """Non-pro-rata selling exhausts the first source fully before touching the next."""
    balances = {0: arr(0.0), 1: arr(5000.0), 2: arr(50000.0)}
    sources = [acct(1), acct(2)]  # already in sell order
    flow = apply_sweep(balances, 0, sources, target=12000.0, deadband=1.5, pro_rata=False)
    assert balances[1] == pytest.approx(0.0)
    assert balances[2] == pytest.approx(43000.0)
    assert flow[1] == pytest.approx(-5000.0)
    assert flow[2] == pytest.approx(-7000.0)


def test_selling_is_capped_at_what_exists() -> None:
    """Best-effort: the engine does not invent money, so cash stays short."""
    balances = {0: arr(-5000.0), 1: arr(1000.0)}
    apply_sweep(balances, 0, [acct(1)], target=20000.0, deadband=1.5, pro_rata=True)
    assert balances[1] == pytest.approx(0.0)
    assert balances[0] == pytest.approx(-4000.0)


def test_a_negative_source_balance_is_never_sold_into() -> None:
    """Only positive balances contribute; a negative one must not be driven further down."""
    balances = {0: arr(0.0), 1: arr(-3000.0), 2: arr(10000.0)}
    apply_sweep(balances, 0, [acct(1), acct(2)], target=5000.0, deadband=1.5, pro_rata=True)
    assert balances[1] == pytest.approx(-3000.0)
    assert balances[2] == pytest.approx(5000.0)


def test_no_sources_leaves_everything_alone() -> None:
    """An empty source list is a no-op, even with a cash deficit."""
    balances = {0: arr(-1000.0)}
    assert apply_sweep(balances, 0, [], target=5000.0, deadband=1.5, pro_rata=True) == {}
    assert balances[0] == pytest.approx(-1000.0)


# --- buying ---


def test_surplus_above_the_deadband_is_invested_pro_rata() -> None:
    """Cash above the deadband threshold is invested pro rata across buy targets."""
    balances = {0: arr(20000.0), 1: arr(60000.0), 2: arr(20000.0)}
    flow = apply_sweep(balances, 0, [acct(1), acct(2)], target=10000.0, deadband=1.5, pro_rata=True)
    # threshold is 10000 * 1.5 = 15000, so 5000 is invested 75/25.
    assert balances[0] == pytest.approx(15000.0)
    assert flow[1] == pytest.approx(3750.0)
    assert flow[2] == pytest.approx(1250.0)


def test_cash_inside_the_deadband_produces_no_trade_at_all() -> None:
    """Cash within the deadband triggers neither a sale nor a purchase."""
    balances = {0: arr(12000.0), 1: arr(50000.0)}
    flow = apply_sweep(balances, 0, [acct(1)], target=10000.0, deadband=1.5, pro_rata=True)
    assert balances[0] == pytest.approx(12000.0)
    assert balances[1] == pytest.approx(50000.0)
    assert flow[1] == pytest.approx(0.0)


def test_buying_is_pro_rata_even_under_a_priority_sell_order() -> None:
    """The order is a withdrawal strategy; there is no deposit order."""
    balances = {0: arr(20000.0), 1: arr(60000.0), 2: arr(20000.0)}
    flow = apply_sweep(
        balances, 0, [acct(1), acct(2)], target=10000.0, deadband=1.5, pro_rata=False
    )
    assert flow[1] == pytest.approx(3750.0)
    assert flow[2] == pytest.approx(1250.0)


def test_surplus_splits_evenly_when_every_buy_target_is_empty() -> None:
    """A pro-rata share of nothing is nothing, so an empty portfolio never starts.

    Same rule the frontend's `allocationScenarios` uses for an empty side: with no
    weights to go by, split evenly. Otherwise a household that opens a brokerage account
    at zero and saves into cash never invests a cent.
    """
    balances = {0: arr(20000.0), 1: arr(0.0)}
    apply_sweep(balances, 0, [acct(1)], target=1000.0, deadband=1.5, pro_rata=True)
    assert balances[0] == pytest.approx(1500.0)
    assert balances[1] == pytest.approx(18500.0)


def test_an_even_split_reaches_every_empty_buy_target() -> None:
    """Two empty targets get half the surplus each, not all of it into the first."""
    balances = {0: arr(20000.0), 1: arr(0.0), 2: arr(0.0)}
    flow = apply_sweep(balances, 0, [acct(1), acct(2)], target=1000.0, deadband=1.5, pro_rata=True)
    assert flow[1] == pytest.approx(9250.0)
    assert flow[2] == pytest.approx(9250.0)


# --- vectorisation ---


def test_runs_sell_and_buy_independently_in_the_same_month() -> None:
    """Run 0 is short and must sell; run 1 is flush and must invest.

    One call, no Python loop over runs.
    """
    balances = {0: arr(0.0, 30000.0), 1: arr(50000.0, 50000.0)}
    apply_sweep(balances, 0, [acct(1)], target=arr(10000.0, 10000.0), deadband=1.5, pro_rata=True)
    assert balances[0] == pytest.approx(arr(10000.0, 15000.0))
    assert balances[1] == pytest.approx(arr(40000.0, 65000.0))


@pytest.mark.parametrize("cash", [10000.0, 12000.0, 15000.0])
def test_cash_inside_its_band_moves_nothing(cash: float) -> None:
    """At the floor, between floor and threshold, or at the threshold: no trade.

    Every source still gets a zero flow, so the caller can treat the result uniformly.
    """
    balances = {0: arr(cash, cash), 1: arr(50000.0, 0.0), 2: arr(20000.0, 5.0)}
    flow = apply_sweep(
        balances, 0, [acct(1), acct(2)], target=10000.0, deadband=1.5, pro_rata=False
    )
    assert set(flow) == {1, 2}
    for moved in flow.values():
        np.testing.assert_array_equal(moved, arr(0.0, 0.0))
    np.testing.assert_array_equal(balances[0], arr(cash, cash))
    np.testing.assert_array_equal(balances[1], arr(50000.0, 0.0))
