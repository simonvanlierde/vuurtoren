"""The projection engine.

One code path: the deterministic projection is the Monte Carlo run with n_runs=1 and a
constant returns provider. Every balance is an array of shape (n_runs,).
"""

import re
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Literal

import numpy as np

from vuurtoren.domain import (
    Account,
    AccountKind,
    BuyProperty,
    CashFlow,
    CashFlowKind,
    ChangeTaxResidence,
    ContributionChange,
    ExpenseChange,
    ExtraRepayment,
    Household,
    IncomeChange,
    LumpSumIn,
    LumpSumOut,
    Milestone,
    Person,
    Retire,
    ScenarioOverrides,
    SellProperty,
    TaxOverrides,
)
from vuurtoren.mortgage import annuity_payment
from vuurtoren.returns import ReturnsProvider, fixed_returns, gaussian_returns
from vuurtoren.sweep import SweepOrder, apply_sweep, sellable_accounts
from vuurtoren.tax.household import HouseholdTax
from vuurtoren.tax.overlay import PersonSlice, TreatmentMaps, overlays_for
from vuurtoren.tax.regime import TaxRegime, YearState, regime_for


@dataclass(frozen=True)
class Assumptions:
    """The projection's economic and behavioural dials, with the defaults the app ships.

    Frozen: `scenarios.apply_scenario` builds a modified copy rather than mutating the
    baseline, so two scenarios projected back-to-back cannot leak into each other.
    """

    inflation: float = 0.02
    swr: float = 0.04
    coast_return: float = 0.06
    """Assumed nominal return when projecting whether today's capital coasts to FI."""
    coast_target_age: int = 67
    """The age (of the youngest person) by which coasting capital must reach the FIRE
    number. Coast-FIRE promises "you could stop saving today and still retire on time",
    so the runway ends at a retirement age, not at life expectancy.

    # NOTE: a stored age, not the AOW-derived pension date. Deriving it via
    # regime.state_pension_date, as the pension unlock does, would be more faithful.
    """
    house_appreciation: float = 0.02
    state_pension_growth_months_per_decade: int = 3
    """Months the state pension age drifts later per decade of birth year.

    Named for the seam, not for the Dutch instrument behind it: `TaxRegime.state_pension_date`
    takes it, and Austria's flat 65 ignores it entirely.
    """
    index_tax_allowances: bool = True

    usd_to_eur: Decimal = Decimal("0.851")
    """Euros per dollar — the assumed **yearly average** rate, which is the one the IRS
    mandates for the arithmetic that uses it.

    Direction, because getting it backwards is the classic error and this repo has already
    written it down once for the FBAR feed: this is euros per *one dollar*, the same
    convention as `prices.py`'s `fx_rate_to_eur`. Inverting it would move every US
    threshold by ~38 % in the wrong direction.

    **Why an average and not a spot rate.** § 986(a)(1)(A) requires foreign income taxes
    claimed as a credit to be translated at the average rate for the year they relate to,
    and Publication 54 lets income received evenly through the year use the yearly average
    too — which a projection's income is by construction, since it is an annual figure with
    no dates inside it. So the average is both the mandated rule and the only one a
    forward projection can honestly apply.

    **Why it is flat, and why that is not laziness.** No structural exchange-rate model
    beats a random walk out of sample (Meese & Rogoff, 1983, and it has held up), and a
    random walk's forecast is today's rate carried forward unchanged. Holding it flat is
    the best available forecast rather than an absence of one. A user who disagrees moves
    the dial.

    The default is the last rate this repo has a dated source for — the Treasury Reporting
    Rate of Exchange at 2025-12-31, recorded in `docs/decisions.md`. It is a *dial*, not a
    tax figure, so it carries no `Provenance`: nothing about 2065 can be sourced.
    """

    # --- cash buffer (the monthly sweep step) ---
    cash_buffer_mode: Literal["months", "fixed", "off"] = "months"
    """"months" sizes the buffer from spending and self-scales with inflation; "fixed"
    is a flat amount; "off" skips the sweep entirely.

    An explicit mode rather than `cash_buffer_fixed: Decimal | None` where non-None
    wins: that idiom silently ignores whichever field lost, and a user who sets both
    gets no signal about which one is live.

    Note that "fixed" with `cash_buffer_fixed = 0` is a hard overdraft floor *and*
    sweeps every positive euro of cash into investments each month, since the buy
    threshold is `0 * deadband`. Coherent, but it overrides the household's own
    CONTRIBUTION flows in practice.
    """
    cash_buffer_months: float = 6.0
    cash_buffer_fixed: Decimal = Decimal(0)
    cash_buffer_inflation_linked: bool = True
    """Fixed mode only. A flat nominal buffer decays to roughly half its real value over
    forty years, and that decay would be invisible in every chart."""
    cash_buffer_deadband: float = 1.5
    """Invest only above `target * deadband`, so the engine is not trading every month
    over rounding. Selling has no deadband: the target is a hard floor."""
    cash_sweep_order: SweepOrder = "pro_rata"

    def __post_init__(self) -> None:
        # Validated here because `ScenarioOverrides.assumptions` is `dict[str, object]`,
        # so a typo'd mode or a nonsense number arrives from the API as an ordinary
        # value. A deadband below 1 makes the sell and buy thresholds overlap and the
        # engine churns every month; a negative target makes `surplus` exceed `cash` and
        # the sweep invests money that does not exist.
        if self.cash_buffer_mode not in ("months", "fixed", "off"):
            msg = f"unknown cash_buffer_mode {self.cash_buffer_mode!r}"
            raise ValueError(msg)
        if self.cash_sweep_order not in ("pro_rata", "safest_first", "riskiest_first"):
            msg = f"unknown cash_sweep_order {self.cash_sweep_order!r}"
            raise ValueError(msg)
        if self.cash_buffer_deadband < 1.0:
            msg = f"cash_buffer_deadband must be >= 1, got {self.cash_buffer_deadband}"
            raise ValueError(msg)
        if self.cash_buffer_months < 0 or self.cash_buffer_fixed < 0:
            msg = "the cash buffer target must not be negative"
            raise ValueError(msg)
        # Zero or negative would collapse every dollar threshold to nothing or flip its
        # sign, and both fail far downstream — inside a tax ladder, as a charge nobody
        # can explain.
        if self.usd_to_eur <= 0:
            msg = f"usd_to_eur must be a positive rate, got {self.usd_to_eur}"
            raise ValueError(msg)


@dataclass(frozen=True)
class PlanInput:
    """Everything the engine needs, as plain values. Built by the API layer from the DB."""

    household: Household
    people: list[Person]
    accounts: list[Account]
    cash_flows: list[CashFlow]
    milestones: list[Milestone]
    start: date
    assumptions: Assumptions = field(default_factory=Assumptions)


@dataclass(frozen=True)
class FireMetrics:
    """The FI/FIRE figures derived from a finished projection."""

    fire_number: float
    fi_dates: list[date | None]
    """Per run, the month FI is first reached — None if this run never gets there.

    Plural and per-run deliberately: with n_runs > 1 there is no single FI date, and
    reporting run 0's as the household's would hide the spread the Monte Carlo exists
    to show.
    """
    coast_fire_dates: list[date | None]
    """Per run, the month today's capital would coast to FI unaided. See `fi_dates`."""
    savings_rate: float
    fire_usable: np.ndarray
    """Capital that can actually fund retirement, shape (n_runs, n_months)."""
    net_swr: float
    """Gross SWR minus the Box 3 drag on a pure investment portfolio in the FI year — the
    honest "4% after Box 3". Isolated from bank/debt/mortgage, which the
    question excludes; forfaitair pre-2028, WWR after. The FI year (not year 0) so the drag
    is on the retirement-sized pot, not a still-accumulating one below the allowance.
    Equals `swr` when the plan holds no Box 3 investments."""


@dataclass(frozen=True)
class Projection:
    """Everything `project` computed, as numpy arrays the API layer serialises.

    Index 0 of every monthly series is the opening position, before the first month's
    activity, so `months` is one longer than the number of months actually simulated.
    """

    months: list[date]
    net_worth: np.ndarray
    inflation_factor: np.ndarray
    """Cumulative price level per month index, shape (n_months,); 1.0 at index 0.

    Deterministic even under Monte Carlo — inflation is not sampled — so it is
    one 1-D series, not per-run. Divide any nominal series by this for a real,
    "today's euros" view; a real/nominal mix on one axis is worse than either."""
    components: dict[str, np.ndarray]
    tax_paid: dict[str, np.ndarray]
    """Per tax year, shape (n_runs, n_years).

    Keys: "investment_tax", "housing_adjustment", "withdrawal_tax".

    Country-neutral names: the engine does not know these are Box 3 and HRA.
    """
    one_off_costs: dict[str, np.ndarray]
    """Shape (n_runs,). Keys: "transfer_tax"."""
    flow_totals: dict[str, np.ndarray]
    """Monthly flow totals, shape (n_records,), run-independent (flows and the
    mortgage are the same in every run). Keys: "income", "expenses", "contributions",
    "housing" (mortgage payment actually debited plus VvE). Index 0 is the opening
    position and always 0. View 6's chart data."""
    investment_income: np.ndarray
    """Per-month euro gain on liquid investments, shape (n_runs, n_records), net of TER.
    The crossover chart's passive-income line; per-run because returns are sampled."""
    fire: FireMetrics
    account_balances: dict[int, np.ndarray]
    """Per account id, the monthly balance series, shape (n_runs, n_records).

    Already computed for the cash-shortfall check and the FIRE metrics, and exposed rather
    than recomputed — the reporting layer needs a *peak during the year* per account, which
    `components` cannot give it because that aggregates by economic kind and throws the
    account away. Read-only output: nothing in the engine reads this back.
    """
    cash_shortfall: list[date | None]
    """Per run, the month the cash account first goes negative — None if it never does.

    The buffer (step 8) sells investments to keep cash off the floor, but it is
    best-effort: the engine does not invent money. A date here therefore means the
    eligible investments ran dry too, and every figure after it describes a household
    that is genuinely insolvent rather than one the engine simply never rebalanced.
    """

    def success_probability(self, min_end_net_worth: float | None = None) -> float:
        """Fraction of runs that never ran the cash account dry.

        With `min_end_net_worth` set (the bequest floor / die-with-zero knob), a run must
        also finish with at least that much net worth: success becomes leaving something
        behind, not merely staying solvent. None keeps the plain solvency definition.
        """
        n_runs = self.net_worth.shape[0]
        solvent = (d is None for d in self.cash_shortfall)
        if min_end_net_worth is None:
            return sum(solvent) / n_runs
        end = self.net_worth[:, -1]
        return sum(s and end[r] >= min_end_net_worth for r, s in enumerate(solvent)) / n_runs

    def solvent_fraction(self) -> list[float]:
        """Fraction of runs still solvent at each month.

        The other half of "rich, broke or dead". A run counts as solvent for every month
        strictly before its `cash_shortfall`, and broke from then on: once the cash account
        is empty the figures after it describe a household on an overdraft, so the plan
        failed there and stayed failed.
        """
        n_runs = self.net_worth.shape[0]
        broke_from = np.full(n_runs, len(self.months), dtype=int)
        for r, d in enumerate(self.cash_shortfall):
            if d is not None:
                broke_from[r] = self.months.index(d)
        month_idx = np.arange(len(self.months))[None, :]
        counts = (month_idx < broke_from[:, None]).sum(axis=0).astype(float).tolist()
        return [n / n_runs for n in counts]


def _age_on(birth_date: date, when: date) -> int:
    """Age in whole years on `when`."""
    return (
        when.year - birth_date.year - ((when.month, when.day) < (birth_date.month, birth_date.day))
    )


def _month_starts(start: date, count: int) -> list[date]:
    out = []
    y, m = start.year, start.month
    for _ in range(count):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _accrue_to_maps(
    maps: TreatmentMaps,
    account: Account,
    *,
    balance: np.ndarray,
    income: np.ndarray,
    fund_gains: np.ndarray,
    growth: np.ndarray,
    realized_gain: np.ndarray,
    key: str | None,
) -> None:
    """Add one account's year to a `TreatmentMaps`, under `key`.

    `key` is the account's overlay treatment for a `CitizenshipOverlay`'s maps (which may
    never read an `nl.*` key) and its tax treatment for the residence regime's. `None` —
    no overlay classification — is carried as a key rather than dropped, so an
    unclassified account's income still reaches the overlay.

    A yield is recorded only when the account declares one — a treatment absent from a map
    means "no such income", which is not the same as zero.

    Mutates `maps`. `TreatmentMaps` is frozen, but its dicts are not, which is what makes
    accumulating in place possible; `dataclasses.replace` per account would allocate four
    dicts per account per year for nothing.
    """
    maps.balances[key] = maps.balances.get(key, np.zeros_like(balance)) + balance
    if account.distribution_yield:
        maps.income[key] = maps.income.get(key, np.zeros_like(income)) + income
    if account.fund_realized_gain_yield:
        maps.fund_realized_gains[key] = (
            maps.fund_realized_gains.get(key, np.zeros_like(fund_gains)) + fund_gains
        )
    maps.value_growth[key] = maps.value_growth.get(key, np.zeros_like(growth)) + growth
    if np.any(realized_gain != 0.0):
        maps.realized_gains[key] = (
            maps.realized_gains.get(key, np.zeros_like(realized_gain)) + realized_gain
        )


def _horizon_months(plan: PlanInput) -> int:
    """Months from `plan.start` to the youngest person's life-expectancy birthday month."""
    youngest_birth_date = max(p.birth_date for p in plan.people)
    end_year = youngest_birth_date.year + plan.household.life_expectancy_age
    months = (end_year - plan.start.year) * 12 + (youngest_birth_date.month - plan.start.month)
    if months <= 0:
        msg = (
            f"the horizon ends before it starts: the youngest person was born "
            f"{youngest_birth_date} and life_expectancy_age is "
            f"{plan.household.life_expectancy_age}, putting the end of the projection in "
            f"{end_year}-{youngest_birth_date.month:02d}, but it starts {plan.start}"
        )
        raise ValueError(msg)
    return months


def projection_months(plan: PlanInput) -> list[date]:
    """The month labels `project(plan)` reports, without running the projection.

    One longer than the months simulated: index 0 is the opening position.
    """
    return _month_starts(plan.start, _horizon_months(plan) + 1)


def _first_hit(mask: np.ndarray, months: list[date]) -> list[date | None]:
    """Per run, the month where `mask` first holds — None where it never does.

    `argmax` on a boolean row returns 0 both for "first column" and for "no True at
    all", so the `any` result is what distinguishes them.
    """
    ever = mask.any(axis=1)
    first = mask.argmax(axis=1)
    return [months[int(i)] if hit else None for i, hit in zip(first, ever, strict=True)]


def flow_active(flow: CashFlow, when: date) -> bool:
    """Whether `flow` runs in the month starting `when`; both date bounds are inclusive."""
    if flow.start_date is not None and when < flow.start_date:
        return False
    return not (flow.end_date is not None and when > flow.end_date)


def _parse_age_override(text: str) -> int:
    """'67y' / '67y3m' (Person.pension_age_override) -> months."""
    m = re.fullmatch(r"(\d+)y(?:(\d+)m)?", text)
    if m is None:
        msg = f"pension_age_override {text!r} is not of the form '67y' or '67y3m'"
        raise ValueError(msg)
    return int(m.group(1)) * 12 + int(m.group(2) or 0)


def _month_after(birth: date, months: int) -> date:
    """The month-start `months` after `birth` — the engine works in whole months."""
    total = birth.month - 1 + months
    return date(birth.year + total // 12, total % 12 + 1, 1)


@dataclass
class _FlowState:
    """The current amount of every cash flow, re-based by change milestones.

    `base` is the amount as quoted at `base_factor`'s point in time: after an
    Income/Expense/ContributionChange, the new figure is in the euros of the change
    month, so an inflation-linked flow inflates from there rather than from the
    projection start. `stopped` holds flows ended by a Retire milestone.
    """

    base: dict[int, float]
    base_factor: dict[int, float]
    stopped: set[int] = field(default_factory=set)

    @classmethod
    def initial(cls, flows: list[CashFlow]) -> _FlowState:
        return cls(
            {f.id: float(f.amount_monthly) for f in flows},
            dict.fromkeys((f.id for f in flows), 1.0),
        )

    def amount(self, flow: CashFlow, inflation_factor: float) -> float:
        if flow.id in self.stopped:
            return 0.0
        amount = self.base[flow.id]
        if flow.inflation_linked:
            amount *= inflation_factor / self.base_factor[flow.id]
        return amount

    def change(self, flow_id: int, new_amount: Decimal, inflation_factor: float) -> None:
        self.base[flow_id] = float(new_amount)
        self.base_factor[flow_id] = inflation_factor


def _index_inflation(assumptions: Assumptions) -> float | None:
    """The rate tax allowances are indexed by, or None when indexing is off."""
    return assumptions.inflation if assumptions.index_tax_allowances else None


def _claim_gift(
    amount: Decimal,
    recipient: Person,
    when: date,
    *,
    regime: HouseholdTax,
    onetime_used: set[int],
) -> None:
    """Fail loudly on a gift its exemption does not cover.

    Gift tax on the excess is deliberately not modelled — only gifts inside the
    exemption are — and silently accepting a larger one would understate tax.
    """
    free = regime.gift_tax_free_amount(
        amount,
        recipient_birth_date=recipient.birth_date,
        gift_date=when,
        onetime_used=recipient.id in onetime_used,
    )
    if free < amount:
        msg = (
            f"a gift of {amount} to {recipient.name!r} in {when.year} exceeds its tax-free "
            f"exemption of {free}; gift tax on the excess is not modelled — reduce the gift"
        )
        raise ValueError(msg)
    # The one-time exemption is consumed only by a gift the annual one does not cover: a
    # gift inside the annual exemption needs no claim, and marking it used would refuse a
    # later gift the recipient is still entitled to.
    annual_only = regime.gift_tax_free_amount(
        amount,
        recipient_birth_date=recipient.birth_date,
        gift_date=when,
        onetime_used=True,
    )
    if annual_only < amount:
        onetime_used.add(recipient.id)


def _buffer_target(
    plan: PlanInput,
    when: date,
    inflation_factor: float,
    fixed_outflow: float,
    flows: _FlowState | None = None,
) -> float:
    """How much cash the household wants on hand in month `when`.

    Run-independent — spending, the mortgage payment and the VvE are the same in every
    run — so this returns a scalar and numpy broadcasts it against the (n_runs,)
    balances. `fixed_outflow` is the month's non-flow outflow (mortgage payment + VvE).

    In months mode the expense side is computed with the same rule step 2 uses to
    debit: each active EXPENSE flow at its current `_FlowState` amount, inflated only
    where `inflation_linked` is set. A parallel rule here could drift from what is
    actually spent — which is why the engine passes its live flow state in.
    """
    a = plan.assumptions
    if a.cash_buffer_mode == "fixed":
        target = float(a.cash_buffer_fixed)
        return target * inflation_factor if a.cash_buffer_inflation_linked else target

    # The mortgage is debited in step 6 and is never an EXPENSE flow, so counting only
    # EXPENSE flows would size an owner's buffer as if its largest outflow did not
    # exist. Rent is an ordinary EXPENSE flow and is already counted, so leaving the
    # mortgage out would hand the buy scenario a smaller buffer than the rent scenario
    # as a pure artefact.
    state = flows if flows is not None else _FlowState.initial(plan.cash_flows)
    outflow = fixed_outflow
    for flow in plan.cash_flows:
        if flow.kind is not CashFlowKind.EXPENSE or not flow_active(flow, when):
            continue
        outflow += state.amount(flow, inflation_factor)
    return a.cash_buffer_months * outflow


_MORTGAGE_REPAID = 1e-6
"""Below this a mortgage counts as repaid, not outstanding. Float amortisation need not
land exactly on zero, and a stray fraction of a cent must not read as a live mortgage."""

_COMPONENTS = ("liquid_investments", "cash", "home_equity", "pension", "debt")


def _apply_basis_move(
    basis: dict[int, np.ndarray],
    balances: dict[int, np.ndarray],
    account_id: int,
    delta: np.ndarray,
) -> np.ndarray:
    """Fold one sweep move into an account's cost basis; return the gain it realized.

    `delta` is signed as the sweep applied it, and `balances` already includes it, so the
    pre-move balance is `balance - delta`. A buy adds its full amount to the basis and
    realizes nothing. A sale of `w` from a position worth `v` consumes `basis * w / v` —
    the moving-average method — and realizes `w` minus that.

    Returns an `(n_runs,)` array, zero in runs that bought or did nothing. A position at
    or below zero has no basis left to apportion, so its sale is treated as pure gain
    rather than dividing by zero.
    """
    if not np.any(delta < 0.0):
        # A pure buy: the general case below reduces to exactly this.
        basis[account_id] = basis[account_id] + delta
        return np.zeros_like(delta)
    before = balances[account_id] - delta
    bought = np.maximum(delta, 0.0)
    sold = np.maximum(-delta, 0.0)

    sellable = before > 0.0
    fraction = np.where(sellable, sold / np.where(sellable, before, 1.0), 0.0)
    # Selling the whole position must consume the whole basis, never more.
    consumed = np.minimum(basis[account_id] * fraction, basis[account_id])
    consumed = np.where(sold > 0.0, consumed, 0.0)

    basis[account_id] = basis[account_id] + bought - consumed
    return np.where(sold > 0.0, sold - consumed, 0.0)


def _component_of(account: Account) -> str:
    """Classify by economic kind only. The engine must never read tax_treatment."""
    match account.kind:
        case AccountKind.PENSION:
            return "pension"
        case AccountKind.REAL_ESTATE:
            return "home_equity"
        case AccountKind.DEBT:
            return "debt"
        case AccountKind.CASH:
            return "cash"
        case _:
            return "liquid_investments"


def _fire_metrics(
    plan: PlanInput,
    months: list[date],
    balances_history: dict[int, np.ndarray],
    components: dict[str, np.ndarray],
    n_runs: int,
    investment_drag: np.ndarray,
    year_index: dict[int, int],
    price_level: np.ndarray,
) -> FireMetrics:
    n_months = len(months)
    usable = components["liquid_investments"] + components["cash"]

    # Pension counts only once it has unlocked: the classic bug in this class of tool.
    for account in plan.accounts:
        if account.kind is not AccountKind.PENSION or account.id is None:
            continue
        unlocked = np.array(
            [
                1.0 if account.liquid_from is None or m >= account.liquid_from else 0.0
                for m in months
            ]
        )
        usable = usable + balances_history[account.id] * unlocked

    # Only flows active at the projection start: the FIRE number and savings rate are
    # point-in-time figures, and a flow that already ended (or has not started yet)
    # would distort them for the whole projection.
    active = [f for f in plan.cash_flows if flow_active(f, plan.start)]
    monthly_expenses = sum(
        float(f.amount_monthly) for f in active if f.kind is CashFlowKind.EXPENSE
    )
    monthly_income = sum(float(f.amount_monthly) for f in active if f.kind is CashFlowKind.INCOME)
    monthly_saved = monthly_income - monthly_expenses
    fire_number = monthly_expenses * 12 / plan.assumptions.swr
    savings_rate = monthly_saved / monthly_income if monthly_income > 0 else 0.0

    fi_dates: list[date | None] = [None] * n_runs
    coast_dates: list[date | None] = [None] * n_runs
    if fire_number > 0:
        # The FIRE number is in `plan.start` euros and `usable` is nominal, so the pot is
        # deflated to the same euros first. Compared nominally, more inflation would reach
        # FI sooner: it inflates the pot and leaves the target where it was.
        real_usable = usable / price_level
        # An expense that is not inflation-linked stays flat in nominal euros, so in
        # start-year euros its share of the target shrinks with the price level.
        unlinked = sum(
            float(f.amount_monthly)
            for f in active
            if f.kind is CashFlowKind.EXPENSE and not f.inflation_linked
        )
        real_target = fire_number - unlinked * 12 / plan.assumptions.swr * (1 - 1 / price_level)
        fi_dates = _first_hit(real_usable >= real_target, months)
        # The coasting runway ends at the coast target age, not at life expectancy:
        # capital that only reaches the FIRE number by compounding to age 95 is not
        # "stop saving today and still retire on time". Anchored to the youngest
        # person, the same convention the horizon uses; from the target month on the
        # factor is 1 and coasting degenerates into plain FI.
        birth = max(p.birth_date for p in plan.people)
        target = date(birth.year + plan.assumptions.coast_target_age, birth.month, 1)
        target_idx = (target.year - months[0].year) * 12 + (target.month - months[0].month)
        years_left = np.maximum(0, target_idx - np.arange(n_months)) / 12
        # `coast_return` is nominal, so the real growth to the target date nets out the
        # inflation over the same years — the same price level the pot was deflated by.
        coast_factor = (
            (1.0 + plan.assumptions.coast_return) / (1.0 + plan.assumptions.inflation)
        ) ** years_left
        # Coasting is judged against the target as it stands at the coast target month.
        coast_month = np.clip(np.maximum(np.arange(n_months), target_idx), 0, n_months - 1)
        coast_dates = _first_hit(real_usable * coast_factor >= real_target[coast_month], months)

    # Net SWR = gross SWR minus the Box 3 drag on the *retirement* portfolio, i.e. the drag
    # in the year FI is reached (run 0's, or the last year if FI never comes). Year 0's drag
    # would read ~0 while the pot still sits under the Box 3 allowance — true today but not
    # the honest "4% after Box 3" for a pot that will be taxed once it is large enough.
    fi = fi_dates[0]
    drag_year = year_index[fi.year] if fi is not None and fi.year in year_index else -1
    net_swr = plan.assumptions.swr - float(np.mean(investment_drag[:, drag_year]))

    return FireMetrics(
        fire_number=fire_number,
        fi_dates=fi_dates,
        coast_fire_dates=coast_dates,
        savings_rate=savings_rate,
        fire_usable=usable,
        net_swr=net_swr,
    )


@dataclass
class _Home:
    """The one property the engine models, and its mortgage.

    Value and mortgage balance are `(n_runs,)` arrays like every balance; the payment,
    rate, extra repayment and VvE are run-independent, so they are scalars.
    """

    value: np.ndarray
    mortgage: np.ndarray
    bought_on: date
    payment: float = 0.0
    rate: float = 0.0
    extra_repayment: float = 0.0
    """Extra monthly principal, once an ExtraRepayment milestone has fired."""
    vve_base: float = 0.0
    vve_base_factor: float = 1.0
    starter_exemption_used: bool = False

    def has_mortgage(self) -> bool:
        return bool(np.any(self.mortgage > _MORTGAGE_REPAID))


_SaleKey = tuple[str, int | None]
"""(tax_treatment, owner_person_id): the pool a within-year loss offset works in."""


@dataclass
class _TaxYear:
    """The running totals of the current tax year. `close` resets them each December.

    Everything here is `(n_runs,)` arrays, accrued month by month and read once, by the
    December step, as a `YearState`.
    """

    n_runs: int
    account_ids: list[int]
    year_start_investments: np.ndarray
    """The actual-return base: the actual-return-treated balances when this year (or the
    projection, or the current residence) opened."""
    net_inflow: np.ndarray = field(init=False)
    """Money moved into (or, negative, out of) the actual-return base this year. Neither
    direction is a gain, so `gain` subtracts it."""
    income: dict[int, np.ndarray] = field(init=False)
    """Ordinary income (dividends, coupons, bank interest) accrued per account."""
    fund_gains: dict[int, np.ndarray] = field(init=False)
    """Gains the fund itself realised by trading, per account."""
    growth: dict[int, np.ndarray] = field(init=False)
    """The year's growth from returns alone, per account."""
    earned_income: dict[int | None, np.ndarray] = field(init=False)
    """Earned income per person, for a citizenship overlay and for a payout taxed on top
    of it; None holds the income flows nobody owns. Household-level income is
    `flow_totals["income"]`; this is the same money attributed to whoever earns it."""
    interest: np.ndarray = field(init=False)
    """Mortgage interest paid this year."""
    sold_home_value: np.ndarray = field(init=False)
    """A home sold this year, as the WOZ that pro-rates its forfait: value at sale times
    the months owned / 12. Below the forfait's upper threshold that is exactly the
    pro-rated forfait the regime would charge."""
    realized_gain_by_account: dict[int, np.ndarray] = field(init=False)
    """Per account rather than per sale pool: a citizenship overlay groups by its own
    classification, and only the account knows which that is. Charged annually, not per
    sale — see `TreatmentMaps.realized_gains`."""
    realized_gain: dict[_SaleKey, np.ndarray] = field(init=False)
    withdrawn: dict[_SaleKey, np.ndarray] = field(init=False)
    withdrawal_tax_charged: dict[_SaleKey, np.ndarray] = field(init=False)
    """Realized gains, gross withdrawals and the withdrawal tax already charged, all
    year-to-date and per sale pool. The tax is computed on the running totals and
    charged as the difference, so a later loss in the same year reduces it — a
    within-year loss offset.

    Keyed by treatment because pools must not mix: Austria is explicit that its 25% and
    27.5% buckets do not pool for loss relief, and a shared accumulator would also
    double-count, every treatment charging on the combined pool while subtracting only
    what it had charged itself. Keyed by owner because the offset is per taxpayer: one
    person's November loss must not reduce the tax on their partner's March gain.
    Austria's Verlustausgleich is explicitly per Steuerpflichtiger and is never pooled
    across spouses."""

    def __post_init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        n = self.n_runs
        self.net_inflow = np.zeros(n)
        self.income = {i: np.zeros(n) for i in self.account_ids}
        self.fund_gains = {i: np.zeros(n) for i in self.account_ids}
        self.growth = {i: np.zeros(n) for i in self.account_ids}
        self.earned_income = {}
        self.interest = np.zeros(n)
        self.sold_home_value = np.zeros(n)
        self.realized_gain_by_account = {}
        self.realized_gain = {}
        self.withdrawn = {}
        self.withdrawal_tax_charged = {}

    def close(self, invested: np.ndarray) -> None:
        """Start the next tax year, its actual-return base opening on `invested`."""
        self._reset()
        self.year_start_investments = invested

    def reopen_base(self, invested: np.ndarray) -> None:
        """Re-open the actual-return base mid-year, as on a change of residence."""
        self.year_start_investments = invested
        self.net_inflow = np.zeros(self.n_runs)

    def add_inflow(self, amount: np.ndarray | float) -> None:
        self.net_inflow = self.net_inflow + amount

    def earn(self, person_id: int | None, amount: float) -> None:
        self.earned_income[person_id] = (
            self.earned_income.get(person_id, np.zeros(self.n_runs)) + amount
        )

    def income_of(self, person_id: int | None, n_people: int) -> np.ndarray:
        """A person's income so far this year plus an equal share of the unowned income.

        Equal because the model records no ownership fractions. Zero for None: a joint
        account's payout has no one person whose income it lands on.
        """
        zero = np.zeros(self.n_runs)
        if person_id is None:
            return zero
        return self.earned_income.get(person_id, zero) + self.earned_income.get(None, zero) / max(
            n_people, 1
        )

    def accrue_return(self, account: Account, before: np.ndarray, after: np.ndarray) -> None:
        """Record one month's return on `account`, which grew from `before` to `after`.

        The income share is accrued on the pre-growth balance. It is a *decomposition* of
        the total return, not an addition: the balance still grows by `return_assumption`
        alone, and this only records how much of that growth a tax authority would call
        income. Growth is the change a unit price would show — deposits and withdrawals
        are applied elsewhere — rather than the change in the holder's stake.
        """
        if account.id is None:
            return
        if account.distribution_yield:
            self.income[account.id] = self.income[account.id] + (
                before * account.distribution_yield / 12.0
            )
        if account.fund_realized_gain_yield:
            self.fund_gains[account.id] = self.fund_gains[account.id] + (
                before * account.fund_realized_gain_yield / 12.0
            )
        self.growth[account.id] = self.growth[account.id] + (after - before)

    def record_sale(self, account_id: int, realized: np.ndarray) -> None:
        self.realized_gain_by_account[account_id] = (
            self.realized_gain_by_account.get(account_id, np.zeros(self.n_runs)) + realized
        )

    def add_sale(self, key: _SaleKey, withdrawn: np.ndarray, realized: np.ndarray) -> None:
        """Add one sale to its pool's year-to-date withdrawn sum and gain."""
        self.withdrawn[key] = self.withdrawn.get(key, np.zeros(self.n_runs)) + withdrawn
        self.realized_gain[key] = self.realized_gain.get(key, np.zeros(self.n_runs)) + realized

    def charge_withdrawal(self, key: _SaleKey, due: np.ndarray) -> np.ndarray:
        """The part of the pool's year-to-date `due` not yet charged; marks it charged."""
        already = self.withdrawal_tax_charged.get(key, np.zeros(self.n_runs))
        self.withdrawal_tax_charged[key] = due
        return due - already

    def year_state(
        self,
        plan: PlanInput,
        balances: dict[int, np.ndarray],
        home_value: np.ndarray,
        regime: HouseholdTax,
        year: int,
    ) -> tuple[YearState, np.ndarray]:
        """The year as the regime sees it, plus the actual-return-treated balance total.

        The engine groups balances by owner and `tax_treatment` and sums them, but does
        not interpret the keys — it hands the mapping to the regime.
        """
        n_runs = self.n_runs
        # Per-person view for a citizenship overlay. Ownership only: the engine says who
        # holds what and stops there, because how much of a joint holding falls inside
        # another country's net is that country's rule (invariant 1 in CONTRIBUTING.md).
        # The same ownership split keyed by tax_treatment feeds the residence regime
        # (`YearState.by_owner`): non-partners are taxed per person.
        owned_maps: dict[int, TreatmentMaps] = {}
        joint_maps = TreatmentMaps()
        by_owner: dict[int | None, TreatmentMaps] = {p.id: TreatmentMaps() for p in plan.people}
        by_owner[None] = TreatmentMaps()
        for account in plan.accounts:
            if account.id is None:
                continue
            target = (
                joint_maps
                if account.owner_person_id is None
                else owned_maps.setdefault(account.owner_person_id, TreatmentMaps())
            )
            year_of_account = {
                "balance": balances[account.id],
                "income": self.income[account.id],
                "fund_gains": self.fund_gains[account.id],
                "growth": self.growth[account.id],
                "realized_gain": self.realized_gain_by_account.get(account.id, np.zeros(n_runs)),
            }
            _accrue_to_maps(target, account, **year_of_account, key=account.overlay_treatment)
            _accrue_to_maps(
                by_owner.setdefault(account.owner_person_id, TreatmentMaps()),
                account,
                **year_of_account,
                key=account.tax_treatment,
            )
        by_person = {
            person.id: PersonSlice(
                person_id=person.id,
                owned=owned_maps.get(person.id, TreatmentMaps()),
                joint=joint_maps,
                earned_income=self.earned_income.get(person.id, np.zeros(n_runs)),
            )
            for person in plan.people
        }

        # One call for all runs: the seam works in (n_runs,) arrays (invariant 6).
        s = YearState(
            year=year,
            home_value=home_value + self.sold_home_value,
            mortgage_interest_paid=self.interest,
            fiscal_partners=plan.household.fiscal_partners,
            by_person=by_person,
            by_owner=by_owner,
        )
        invested = sum(
            (
                v
                for k, v in s.balances_by_treatment.items()
                if k in regime.actual_return_treatments()
            ),
            start=np.zeros(n_runs),
        )
        gain = invested - self.year_start_investments - self.net_inflow
        return replace(s, investment_gain=gain), invested


@dataclass
class _Run:
    """One projection's state, threaded through the monthly steps in `project`.

    Mutable on purpose: each step moves money between the balances it holds. Lives for one
    `project` call only, so nothing in it — the tax-config cache included — can leak
    between scenarios.
    """

    plan: PlanInput
    n_runs: int
    regime: HouseholdTax
    """Replaced at every year end by the composite `close_year` returns, which carries the
    overlays' state into the next year."""
    cash_id: int
    balances: dict[int, np.ndarray]
    basis: dict[int, np.ndarray]
    """Running cost basis per account, for regimes that tax a realized gain rather than
    the gross withdrawal. Seeded from the user's stated `cost_basis`; an account with none
    opens at its own value, i.e. no unrealised gain yet — the neutral assumption, and the
    only one available when nobody recorded what was paid.

    Buys raise it, sells reduce it pro rata, and growth deliberately does not touch it
    (that is the gain). Pro-rata reduction is the moving-average method: it is what
    Austria's gleitender Durchschnittspreis (§ 27a Abs 4 Z 3 EStG) requires, so the
    obvious implementation is also the legally correct one."""
    home: _Home
    tax_year: _TaxYear
    flows: _FlowState
    calc_months: list[date]
    """The month starts simulated. `when` in every step is one of these."""
    year_index: dict[int, int]
    recorded: dict[str, np.ndarray]
    history: dict[int, np.ndarray]
    investment_income: np.ndarray
    """Per-month euro gain on liquid investments — the "passive income" the crossover
    chart crosses against expenses. Captured at the growth step; net of TER."""
    flow_totals: dict[str, np.ndarray]
    tax_paid: dict[str, np.ndarray]
    one_off_costs: dict[str, np.ndarray]
    investment_drag: np.ndarray
    """The Box 3 drag on a pure investment portfolio, per tax year — the net-SWR
    headline's input. Filled each December; `_fire_metrics` reads the FI year's column."""
    accounts_by_id: dict[int, Account] = field(init=False)
    people_by_id: dict[int, Person] = field(init=False)
    state_pension_dates: dict[int, date] = field(init=False)
    """Per person, from the starting regime, like the pension unlock: a mid-projection
    ChangeTaxResidence does not re-derive it."""
    gift_onetime_used: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.accounts_by_id = {a.id: a for a in self.plan.accounts if a.id is not None}
        self.people_by_id = {p.id: p for p in self.plan.people}
        self.state_pension_dates = {
            p.id: _state_pension_date(p, self.plan, self.regime) for p in self.plan.people
        }

    def deposit(self, account_id: int, amount: np.ndarray | float) -> None:
        """Move new money into an account: balance, cost basis and the year's inflow together.

        The inflow is recorded only when the regime counts an actual return on the account.
        New money is not a gain, so it raises the basis in full; and an inflow left out of
        the year's net flows would read as return and be taxed as one.
        """
        self.balances[account_id] += amount
        self.basis[account_id] = self.basis[account_id] + amount
        account = self.accounts_by_id.get(account_id)
        if account is not None and account.tax_treatment in self.regime.actual_return_treatments():
            self.tax_year.add_inflow(amount)

    def investment_base(self) -> np.ndarray:
        """Today's total over the accounts the regime counts an actual return on."""
        return sum(
            (
                self.balances[a.id]
                for a in self.plan.accounts
                if a.id is not None and a.tax_treatment in self.regime.actual_return_treatments()
            ),
            start=np.zeros(self.n_runs),
        )

    def record(self, k: int) -> None:
        """Write the current position into record index `k`."""
        for account in self.plan.accounts:
            if account.id is None:
                continue
            self.recorded[_component_of(account)][:, k] += self.balances[account.id]
            self.history[account.id][:, k] = self.balances[account.id]
        self.recorded["home_equity"][:, k] += self.home.value
        self.recorded["debt"][:, k] -= self.home.mortgage


def project(
    plan: PlanInput,
    *,
    n_runs: int = 1,
    seed: int | None = None,
    returns: ReturnsProvider | None = None,
    tax_overrides: TaxOverrides | None = None,
    regime: TaxRegime | None = None,
) -> Projection:
    """Walk the plan month by month and return the whole projection.

    The deterministic projection is this same code with `n_runs=1` and a constant
    returns provider; every balance is a `(n_runs,)` array throughout. Each month runs
    nine steps in order — flows, milestones, growth, mortgage, December tax,
    the cash-buffer sweep, then record — and the order is load-bearing.

    Args:
        plan: The household, accounts, flows, milestones and assumptions to project.
        n_runs: Number of Monte Carlo runs. 1 is the deterministic projection.
        seed: Seed for the default Monte Carlo provider, so a chart reproduces.
        returns: Monthly returns provider. Defaults to `fixed_returns` for a single run
            and `gaussian_returns(seed)` for more, so `n_runs > 1` never silently
            produces identical runs.
        tax_overrides: The scenario's tax-figure overrides, which the regime reads.
            Every other override group is applied to `plan` by
            `scenarios.apply_scenario` before it gets here.
        regime: Tax regime to start under. Defaults to the household's `tax_country`;
            a ChangeTaxResidence milestone switches it mid-projection.

    Returns:
        The monthly series, per-year tax, one-off costs and FIRE metrics.

    Raises:
        ValueError: A plan the engine cannot run — no CASH account, a horizon that ends
            before it starts, a milestone that fires outside the window or references
            something that does not exist, a gift beyond its exemption, or a mortgage
            that would amortise negatively.
        NotImplementedError: A non-own-occupancy purchase, or a second property bought
            while a mortgage is still outstanding.
    """
    if returns is None:
        # n_runs > 1 with no explicit provider is the Monte Carlo path;
        # forgetting a provider must not silently produce 10,000 identical runs.
        returns = gaussian_returns(seed) if n_runs > 1 else fixed_returns

    run = _open_run(plan, n_runs=n_runs, tax_overrides=tax_overrides, regime=regime)
    plan = run.plan
    # calc_months drives milestone/cash-flow matching (`when` = start of that month).
    # months is the returned, chart-facing labels: one longer, since index 0 holds the
    # true opening position.
    calc_months = run.calc_months
    months = projection_months(plan)
    milestone_fires = _schedule_milestones(run)

    # Geometric, unlike `fixed_returns`, and deliberately so: inflation is a year-on-year
    # price-level change (what CBS and the ECB publish), so a 2% assumption has to deliver
    # exactly 2% over twelve months. A nominal rate like `return_assumption` is a
    # different kind of number and compounds past its own headline figure.
    monthly_inflation = (1.0 + plan.assumptions.inflation) ** (1 / 12) - 1.0

    for i, when in enumerate(calc_months):
        inflation_factor = (1.0 + monthly_inflation) ** i
        # 1-3: income, expenses, contributions.
        _apply_flows(run, when, i, inflation_factor)
        # 4: milestones.
        for fire, milestone in milestone_fires:
            if fire == when:
                _fire_milestone(run, milestone, when, inflation_factor)
        # 5: growth.
        _grow(run, returns, i)
        # 6: mortgage and VvE.
        vve_now = _pay_housing(run, when, i, inflation_factor)
        # 7: annual tax.
        if when.month == 12:
            _close_tax_year(run, when)
        # 8: hold cash inside its buffer. After step 7 for two reasons: the December
        # wealth-tax debit is covered in the month it lands rather than showing a
        # one-month phantom overdraft, and a December sweep then falls into the *next*
        # year's inflow accumulator, which step 7 has just reset.
        if plan.assumptions.cash_buffer_mode != "off":
            _sweep_cash(run, when, inflation_factor, vve_now)
        # 9: record — closing position for month `when`, at record index i + 1
        # (index 0 holds the opening position, recorded by `_open_run`).
        run.record(i + 1)

    net_worth = np.sum(list(run.recorded.values()), axis=0)
    # Per-index price level: index k is k months from start, so (1 + monthly)^k. The
    # in-loop `inflation_factor` deflates within a month; this snapshots the level at
    # each recorded month-end. Both derive from the same geometric monthly rate.
    price_level = (1.0 + monthly_inflation) ** np.arange(len(months))
    fire = _fire_metrics(
        plan,
        months,
        run.history,
        run.recorded,
        n_runs,
        run.investment_drag,
        run.year_index,
        price_level,
    )
    return Projection(
        months=months,
        net_worth=net_worth,
        inflation_factor=price_level,
        components=run.recorded,
        tax_paid=run.tax_paid,
        one_off_costs=run.one_off_costs,
        flow_totals=run.flow_totals,
        investment_income=run.investment_income,
        fire=fire,
        account_balances=run.history,
        cash_shortfall=_first_hit(run.history[run.cash_id] < 0, months),
    )


def _with_pension_unlocks(plan: PlanInput, regime: HouseholdTax) -> PlanInput:
    """`plan` with every owned PENSION account's unlock date filled in.

    A PENSION account with an owner and no stored liquid_from unlocks at the owner's
    derived state-pension date: pension_age_override first, then the regime's schedule
    under the AOW growth assumption. An explicitly stored date is the user's knowledge of
    their own contract and always wins. NOTE: derived from the regime the projection
    starts with; a mid-projection ChangeTaxResidence does not re-derive it.
    """
    people_by_id = {p.id: p for p in plan.people}
    effective_accounts = []
    for account in plan.accounts:
        effective = account
        if (
            account.kind is AccountKind.PENSION
            and account.liquid_from is None
            and account.owner_person_id is not None
        ):
            owner = people_by_id.get(account.owner_person_id)
            if owner is None:
                msg = (
                    f"account {account.name!r} is owned by unknown person {account.owner_person_id}"
                )
                raise ValueError(msg)
            unlock = _state_pension_date(owner, plan, regime)
            effective = account.model_copy(update={"liquid_from": unlock})
        effective_accounts.append(effective)
    return replace(plan, accounts=effective_accounts)


def _state_pension_date(person: Person, plan: PlanInput, regime: HouseholdTax) -> date:
    """The person's state pension date: their pension_age_override, else the regime's."""
    if person.pension_age_override is not None:
        return _month_after(person.birth_date, _parse_age_override(person.pension_age_override))
    return regime.state_pension_date(
        person.birth_date,
        sex=person.sex,
        growth=plan.assumptions.state_pension_growth_months_per_decade,
    )


def check_treatments(accounts: list[Account], valid: frozenset[str], country: str) -> None:
    """Refuse accounts whose tax treatment `country`'s regime does not know.

    Such an account is taxed as nothing, silently. Names every account and its key.
    """
    stale = [f"{a.name} ({a.tax_treatment})" for a in accounts if a.tax_treatment not in valid]
    if stale:
        msg = (
            f"account(s) with a tax treatment {country} does not know: "
            f"{', '.join(stale)}. Retag them for {country}: {sorted(valid)}"
        )
        raise ValueError(msg)


def _open_run(
    plan: PlanInput,
    *,
    n_runs: int,
    tax_overrides: TaxOverrides | None,
    regime: TaxRegime | None,
) -> _Run:
    """Everything `project` sets up before the first month, opening position recorded."""
    active_country = plan.household.tax_country
    # Every projection runs through the composite, even with nothing to compose. Putting
    # the wrapper in unconditionally means the overlay path is the only path and cannot
    # rot unexercised, and a caller-supplied regime simply becomes the residence half of
    # it.
    overlays = overlays_for(
        plan.people, residence=active_country, usd_to_eur=plan.assumptions.usd_to_eur
    )
    for owner, overlay in overlays:
        # Fail before the first month rather than mid-projection: an unelected PFIC is a
        # position the app refuses to model, and the message names the ways out.
        overlay.validate_accounts(plan.accounts, person=owner)
    residence_regime = regime or regime_for(active_country)
    # The household's country can change after its accounts were saved, so this is
    # checked here, not only at save.
    check_treatments(plan.accounts, residence_regime.valid_treatments(), active_country)
    household_tax = HouseholdTax(
        residence=residence_regime,
        overlays=overlays,
        overrides=ScenarioOverrides(tax=tax_overrides) if tax_overrides else None,
        index_inflation=_index_inflation(plan.assumptions),
    )
    plan = _with_pension_unlocks(plan, household_tax)

    n_records = _horizon_months(plan) + 1
    balances: dict[int, np.ndarray] = {
        a.id: np.full(n_runs, float(a.manual_value or Decimal(0)))
        for a in plan.accounts
        if a.id is not None
    }
    cash_ids = [a.id for a in plan.accounts if a.kind is AccountKind.CASH and a.id is not None]
    if not cash_ids:
        msg = "the plan needs at least one CASH account to absorb cash flow"
        raise ValueError(msg)

    calc_months = _month_starts(plan.start, n_records - 1)
    years = sorted({m.year for m in calc_months})
    account_ids = [a.id for a in plan.accounts if a.id is not None]
    run = _Run(
        plan=plan,
        n_runs=n_runs,
        regime=household_tax,
        # Lowest id, not first in the list: `plan.accounts` arrives from an unordered
        # query, and with two CASH accounts of different tax_treatment the choice of which
        # one absorbs every flow moves the Box 3 base. Must not depend on row order.
        cash_id=min(cash_ids),
        balances=balances,
        basis={
            a.id: (
                np.full(n_runs, float(a.cost_basis))
                if a.cost_basis is not None
                else balances[a.id].copy()
            )
            for a in plan.accounts
            if a.id is not None
        },
        home=_Home(value=np.zeros(n_runs), mortgage=np.zeros(n_runs), bought_on=plan.start),
        # Placeholder base, replaced below once the run can sum its own balances.
        tax_year=_TaxYear(n_runs, account_ids, np.zeros(n_runs)),
        flows=_FlowState.initial(plan.cash_flows),
        calc_months=calc_months,
        year_index={y: i for i, y in enumerate(years)},
        recorded={name: np.zeros((n_runs, n_records)) for name in _COMPONENTS},
        history={i: np.zeros((n_runs, n_records)) for i in account_ids},
        investment_income=np.zeros((n_runs, n_records)),
        flow_totals={
            k: np.zeros(n_records) for k in ("income", "expenses", "contributions", "housing")
        },
        tax_paid={
            "investment_tax": np.zeros((n_runs, len(years))),
            "housing_adjustment": np.zeros((n_runs, len(years))),
            "withdrawal_tax": np.zeros((n_runs, len(years))),
        },
        one_off_costs={"transfer_tax": np.zeros(n_runs)},
        investment_drag=np.zeros((n_runs, len(years))),
    )
    # The actual-return base opens at the projection start, so even the first tax year
    # has a computable investment gain — without this, a plan whose first December falls
    # under the WWR regime (start year >= regime_switch_year) cannot be taxed at all. A
    # mid-year start measures the gain since `start`, not since 1 January; the months
    # before the projection are unknowable.
    run.tax_year.year_start_investments = run.investment_base()
    run.record(0)
    return run


def _schedule_milestones(run: _Run) -> list[tuple[date, Milestone]]:
    """Resolve every milestone to the month it fires; fail on anything unmodellable.

    Fails loudly, up front, on anything the engine cannot model or that references
    something that does not exist: nothing silently no-ops. Age-based timing resolves to
    the month the person turns `age_years`. Also checks every flow's target account.
    """
    plan, calc_months = run.plan, run.calc_months
    flows_by_id = {f.id: f for f in plan.cash_flows}
    milestone_fires: list[tuple[date, Milestone]] = []
    for milestone in plan.milestones:
        if milestone.on_date is not None:
            fire = milestone.on_date.replace(day=1)
        elif milestone.age_person_id is not None and milestone.age_years is not None:
            person = run.people_by_id.get(milestone.age_person_id)
            if person is None:
                msg = (
                    f"milestone {milestone.label!r} is timed on the age of unknown "
                    f"person {milestone.age_person_id}"
                )
                raise ValueError(msg)
            fire = date(person.birth_date.year + milestone.age_years, person.birth_date.month, 1)
        else:
            msg = f"milestone {milestone.label!r} has neither on_date nor age-based timing"
            raise ValueError(msg)
        if fire < plan.start.replace(day=1) or fire > calc_months[-1]:
            msg = (
                f"milestone {milestone.label!r} fires {fire}, outside the "
                f"projection window {plan.start} to {calc_months[-1]}"
            )
            raise ValueError(msg)
        milestone_fires.append((fire, milestone))
        _validate_milestone(milestone, run, flows_by_id)
    _check_moves(run, milestone_fires)

    # Same hazard on the flow side: a CONTRIBUTION's destination is indexed directly.
    for flow in plan.cash_flows:
        if flow.target_account_id is not None and flow.target_account_id not in run.accounts_by_id:
            msg = f"cash flow {flow.label!r} targets unknown account {flow.target_account_id}"
            raise ValueError(msg)
    return milestone_fires


def _check_moves(run: _Run, milestone_fires: list[tuple[date, Milestone]]) -> None:
    """Fail up front on a residence change that leaves an account the new regime cannot tax.

    Walks the moves in firing order, applying each one's `retag`, so a return trip is
    checked against the treatments its first leg set.
    """
    treatments = {a.id: a.tax_treatment for a in run.plan.accounts if a.id is not None}
    for _fire, milestone in sorted(milestone_fires, key=lambda f: f[0]):
        params = milestone.params
        if not isinstance(params, ChangeTaxResidence):
            continue
        unknown = sorted(set(params.retag) - set(treatments))
        if unknown:
            msg = f"milestone {milestone.label!r} retags unknown account(s) {unknown}"
            raise ValueError(msg)
        treatments |= params.retag
        valid = regime_for(params.country).valid_treatments()
        stale = [
            f"{run.accounts_by_id[i].name} ({t})" for i, t in treatments.items() if t not in valid
        ]
        if stale:
            msg = (
                f"milestone {milestone.label!r} moves to {params.country}, but these "
                f"accounts keep a tax treatment {params.country} does not know: "
                f"{', '.join(stale)}. Retag them on the milestone: {sorted(valid)}"
            )
            raise ValueError(msg)


_EXPECTED_FLOW_KIND: dict[type[IncomeChange | ExpenseChange | ContributionChange], CashFlowKind] = {
    IncomeChange: CashFlowKind.INCOME,
    ExpenseChange: CashFlowKind.EXPENSE,
    ContributionChange: CashFlowKind.CONTRIBUTION,
}


def _validate_milestone(milestone: Milestone, run: _Run, flows_by_id: dict[int, CashFlow]) -> None:
    params = milestone.params
    if isinstance(params, ChangeTaxResidence):
        try:
            regime_for(params.country)
        except KeyError:
            msg = (
                f"milestone {milestone.label!r} switches tax residence to "
                f"{params.country!r}, for which no tax regime exists"
            )
            raise ValueError(msg) from None
    elif isinstance(params, BuyProperty) and not params.own_occupancy:
        msg = (
            f"a non-own-occupancy purchase is not implemented: milestone "
            f"{milestone.label!r}. A non-primary residence is a Box 3 asset (not the "
            f"Box 1 eigenwoning the engine models); the engine folds every purchase "
            f"into home_value and only models a primary residence."
        )
        raise NotImplementedError(msg)
    elif isinstance(params, IncomeChange | ExpenseChange | ContributionChange):
        flow = flows_by_id.get(params.cash_flow_id)
        if flow is None:
            msg = f"milestone {milestone.label!r} changes unknown cash flow {params.cash_flow_id}"
            raise ValueError(msg)
        expected = _EXPECTED_FLOW_KIND[type(params)]
        if flow.kind is not expected:
            msg = (
                f"milestone {milestone.label!r} needs an {expected.name} flow, but "
                f"cash flow {params.cash_flow_id} is {flow.kind.name}"
            )
            raise ValueError(msg)
    elif isinstance(params, Retire) and params.person_id not in run.people_by_id:
        msg = f"milestone {milestone.label!r} retires unknown person {params.person_id}"
        raise ValueError(msg)
    if (
        isinstance(params, LumpSumIn)
        and params.target_account_id is not None
        and params.target_account_id not in run.accounts_by_id
    ):
        # `balances[target_id] += ...` would raise KeyError halfway through the run, which
        # reaches the API as a 500. Say what is wrong before anything moves.
        msg = f"milestone {milestone.label!r} targets unknown account {params.target_account_id}"
        raise ValueError(msg)


def _apply_flows(run: _Run, when: date, i: int, inflation_factor: float) -> None:
    """Steps 1-3: income, expenses and contributions at their current `_FlowState` amounts.

    Change and retire milestones from earlier months are therefore in force.
    """
    balances, cash_id = run.balances, run.cash_id
    for flow in run.plan.cash_flows:
        if not flow_active(flow, when):
            continue
        amount = run.flows.amount(flow, inflation_factor)
        if flow.kind is CashFlowKind.INCOME:
            balances[cash_id] += amount
            run.flow_totals["income"][i + 1] += amount
            run.tax_year.earn(flow.owner_person_id, amount)
        elif flow.kind is CashFlowKind.EXPENSE:
            balances[cash_id] -= amount
            run.flow_totals["expenses"][i + 1] += amount
        elif flow.kind is CashFlowKind.CONTRIBUTION:
            balances[cash_id] -= amount
            run.flow_totals["contributions"][i + 1] += amount
            if flow.target_account_id is not None:
                run.deposit(flow.target_account_id, amount)


def _fire_milestone(run: _Run, milestone: Milestone, when: date, inflation_factor: float) -> None:
    """Step 4: apply one milestone firing this month."""
    params = milestone.params
    if isinstance(params, ChangeTaxResidence):
        _change_residence(run, params)
    elif isinstance(params, BuyProperty):
        _buy_property(run, params, when, inflation_factor)
    elif isinstance(params, LumpSumIn):
        _receive_lump_sum(run, params, when)
    elif isinstance(params, LumpSumOut):
        run.balances[run.cash_id] -= float(params.amount)
    elif isinstance(params, IncomeChange | ExpenseChange | ContributionChange):
        # Takes effect from the next month: this month's flows already ran in steps 1-3.
        # The new amount is quoted in this month's euros.
        run.flows.change(params.cash_flow_id, params.new_amount_monthly, inflation_factor)
    elif isinstance(params, ExtraRepayment):
        # Runs from here until the mortgage is gone. Deliberately additive, so a second
        # milestone raises the amount rather than replacing it — two "aflossen more"
        # decisions compose the way a user would expect.
        run.home.extra_repayment += float(params.monthly_amount)
    elif isinstance(params, Retire):
        run.flows.stopped.update(
            f.id
            for f in run.plan.cash_flows
            if f.kind is CashFlowKind.INCOME and f.owner_person_id == params.person_id
        )
    elif isinstance(params, SellProperty):
        _sell_property(run, milestone, params, when)


def _change_residence(run: _Run, params: ChangeTaxResidence) -> None:
    country = params.country
    # Treatments are scoped to the country, so the move carries its own retag;
    # `_check_moves` has already proved every account ends on a key the new regime knows.
    if params.retag:
        run.plan = replace(
            run.plan,
            accounts=[
                a.model_copy(update={"tax_treatment": params.retag[a.id]})
                if a.id in params.retag
                else a
                for a in run.plan.accounts
            ],
        )
        run.accounts_by_id = {a.id: a for a in run.plan.accounts if a.id is not None}
    # Only the residence half changes: assigning the bare regime would drop every
    # citizenship overlay, so a US person who emigrated would stop owing the United States
    # anything. The overlays and their carries (credit bank, PFIC pool) move with the
    # composite. Their treaty layer does not re-pick — see `USCitizenshipOverlay.residence`.
    # The residence carry (the Dutch loss pool) waits for a return; see `move_to`.
    run.regime = run.regime.move_to(regime_for(country))
    # The actual-return base is the new regime's own: re-open it on today's balances, as
    # at the projection start. Carried over, it holds whatever the old regime counted —
    # nothing, after a spell under a regime without one — and the first December back
    # would tax the whole portfolio as gain.
    run.tax_year.reopen_base(run.investment_base())


def _buy_property(run: _Run, params: BuyProperty, when: date, inflation_factor: float) -> None:
    home, plan = run.home, run.plan
    if home.has_mortgage():
        msg = (
            "a second BuyProperty while a mortgage is still outstanding is "
            "not supported: the engine models a single mortgage"
        )
        raise NotImplementedError(msg)
    if params.buyer_person_id is None:
        buyer = plan.people[0]
    else:
        buyer = next((p for p in plan.people if p.id == params.buyer_person_id), None)
        if buyer is None:
            msg = (
                f"BuyProperty buyer_person_id {params.buyer_person_id} matches "
                f"no person in the household"
            )
            raise ValueError(msg)
    age = _age_on(buyer.birth_date, when)
    raw_duty, consumed = run.regime.purchase_costs(
        params.price,
        buyer_age=age,
        own_occupancy=params.own_occupancy,
        starter_exemption_used=home.starter_exemption_used,
        mortgage_amount=params.mortgage,
        year=when.year,
    )
    duty = float(raw_duty)
    home.starter_exemption_used = home.starter_exemption_used or consumed
    run.one_off_costs["transfer_tax"] += duty
    if params.gift_used != 0:
        # The gift funds the purchase, and the exemption is claimed by the buyer at the
        # milestone date.
        _claim_gift(
            params.gift_used,
            buyer,
            when,
            regime=run.regime,
            onetime_used=run.gift_onetime_used,
        )
        run.balances[run.cash_id] += float(params.gift_used)
    deposit = float(params.price - params.mortgage)
    run.balances[run.cash_id] -= deposit + duty
    home.value = home.value + float(params.price)
    home.mortgage = home.mortgage + float(params.mortgage)
    home.rate = float(params.annual_rate)
    home.payment = float(annuity_payment(params.mortgage, params.annual_rate, params.term_months))
    home.vve_base = float(params.vve_monthly)
    home.vve_base_factor = inflation_factor
    home.bought_on = when


def _receive_lump_sum(run: _Run, params: LumpSumIn, when: date) -> None:
    target_id = params.target_account_id or run.cash_id
    target = run.accounts_by_id.get(target_id)
    if params.is_gift_exemption:
        # The recipient is the target account's owner; a joint or cash-defaulted gift is
        # claimed by the first person, mirroring BuyProperty's buyer default.
        recipient = run.plan.people[0]
        if target is not None and target.owner_person_id is not None:
            recipient = run.people_by_id.get(target.owner_person_id) or recipient
        _claim_gift(
            params.amount,
            recipient,
            when,
            regime=run.regime,
            onetime_used=run.gift_onetime_used,
        )
    run.deposit(target_id, float(params.amount))


def _sell_property(run: _Run, milestone: Milestone, params: SellProperty, when: date) -> None:
    home = run.home
    if not np.any(home.value > 0.0):
        msg = f"milestone {milestone.label!r} sells a property in {when}, but none is owned"
        raise ValueError(msg)
    # Equity comes back to cash net of the mortgage payoff and selling costs; from here the
    # capital is in the wealth-tax base again, which is the asymmetry rent-vs-buy turns on.
    run.balances[run.cash_id] += home.value - home.mortgage - float(params.costs)
    # The interest paid before the sale is still deductible this year, against a forfait
    # for the months the home was owned. Months Jan..`when`-1: the sale fires at the start
    # of `when`, before that month's payment.
    owned_from = home.bought_on.month if home.bought_on.year == when.year else 1
    run.tax_year.sold_home_value = (
        run.tax_year.sold_home_value + home.value * (when.month - owned_from) / 12
    )
    home.value = np.zeros(run.n_runs)
    home.mortgage = np.zeros(run.n_runs)
    home.payment = 0.0
    home.rate = 0.0
    home.extra_repayment = 0.0
    home.vve_base = 0.0


def _grow(run: _Run, returns: ReturnsProvider, i: int) -> None:
    """Step 5: one month's return on every account.

    No short-circuit on return_assumption == 0.0: a stochastic provider can draw nonzero
    returns for an account whose mean is zero.
    """
    balances = run.balances
    for account in run.plan.accounts:
        if account.id is None:
            continue
        before = balances[account.id].copy()
        # TER is a nominal annual drag (the same convention as `fixed_returns`), so it
        # comes off the monthly gross return as `expense_ratio / 12`, whatever provider
        # produced it.
        balances[account.id] *= 1.0 + returns(account, i, run.n_runs) - account.expense_ratio / 12.0
        run.tax_year.accrue_return(account, before, balances[account.id])
        if _component_of(account) == "liquid_investments":
            # The euro gain this month, net of TER — the crossover chart's passive income.
            run.investment_income[:, i + 1] += balances[account.id] - before


def _pay_housing(run: _Run, when: date, i: int, inflation_factor: float) -> float:
    """Step 6: the mortgage payment, any extra repayment and the VvE; returns the VvE."""
    home, cash_id = run.home, run.cash_id
    if home.payment > 0.0:
        interest = home.mortgage * home.rate / 12
        shortfall = (home.mortgage > 0.0) & (home.payment < interest)
        if np.any(shortfall):
            r = int(np.argmax(shortfall))
            msg = (
                f"in {when} (run {r}) the monthly payment {home.payment} does not "
                f"cover the interest {interest[r]} accrued on a balance of "
                f"{home.mortgage[r]} at {home.rate:.4%}: the mortgage would "
                f"amortise negatively"
            )
            raise ValueError(msg)
        principal = np.minimum(home.payment - interest, home.mortgage)
        had_balance = home.mortgage > 0.0
        home.mortgage = np.maximum(home.mortgage - principal, 0.0)
        run.tax_year.interest += interest
        debit = np.where(had_balance, interest + principal, 0.0)
        # Aflossen: straight off the principal, capped at what is left so a large
        # repayment clears the mortgage rather than overshooting. `payment` is untouched,
        # so the term shortens — see ExtraRepayment.
        if home.extra_repayment > 0.0:
            paid_extra = np.where(had_balance, np.minimum(home.extra_repayment, home.mortgage), 0.0)
            home.mortgage = home.mortgage - paid_extra
            debit = debit + paid_extra
        run.balances[cash_id] -= debit
        # The mortgage is run-independent by construction, so run 0 speaks for all.
        run.flow_totals["housing"][i + 1] += float(debit[0])
    # VvE service costs while a property is owned — part of the net housing cost,
    # inflation-linked from the purchase month like any price-level figure.
    vve_now = (
        home.vve_base * (inflation_factor / home.vve_base_factor) if home.vve_base > 0.0 else 0.0
    )
    if vve_now:
        run.balances[cash_id] -= vve_now
        run.flow_totals["housing"][i + 1] += vve_now
    # Geometric for the same reason as monthly_inflation: house appreciation is a
    # year-on-year price change, not a nominal rate.
    home.value *= (1.0 + run.plan.assumptions.house_appreciation) ** (1 / 12)
    return vve_now


def _close_tax_year(run: _Run, when: date) -> None:
    """Step 7: charge the year's annual taxes, step up cost bases, open the next year.

    Deliberate convention: Box 3 for year Y is assessed here on the 31-Dec-Y balances the
    engine has just finished computing, not the statutory peildatum of 1-Jan-Y. The tax is
    charged in the month it accrues rather than the following spring, when it is actually
    assessed.
    """
    regime = run.regime
    _true_up_withdrawal_tax(run, when.year)
    s, invested = run.tax_year.year_state(run.plan, run.balances, run.home.value, regime, when.year)
    yi = run.year_index[when.year]
    run.tax_paid["investment_tax"][:, yi], run.regime = regime.close_year(s)
    run.tax_paid["housing_adjustment"][:, yi] = regime.annual_housing_adjustment(s)
    run.investment_drag[:, yi] = _investment_drag(run, s, invested)

    run.balances[run.cash_id] -= run.tax_paid["investment_tax"][:, yi]
    run.balances[run.cash_id] += run.tax_paid["housing_adjustment"][:, yi]
    _step_up_basis(run, regime.annual_basis_step_up(s))
    run.tax_year.close(invested)


def _investment_drag(run: _Run, s: YearState, invested: np.ndarray) -> np.ndarray:
    """The Box 3 drag on a *pure* investment portfolio this year, as a rate.

    Bank and debt are zeroed so the allowance and debt-netting don't distort the per-euro
    rate. Uses only the regime protocol, so engine.py stays free of Dutch tax law
    (invariant 1 in CONTRIBUTING.md). `_fire_metrics` reads the FI year's rate, not year
    0's: the drag on the retirement-sized pot is the honest "4% after Box 3", where a
    still-accumulating pot below the allowance reads ~0.
    """
    actual = run.regime.actual_return_treatments()
    # The residence half only: the metric is a residence one, "the 4 % after Box 3".
    inv_only = {
        owner: replace(maps, balances={k: v for k, v in maps.balances.items() if k in actual})
        for owner, maps in s.by_owner.items()
    }
    tax_inv = run.regime.residence.annual_investment_tax(
        replace(s, by_owner=inv_only), run.regime.cfg(s.year)
    )
    return np.where(invested > 0.0, tax_inv / np.where(invested > 0.0, invested, 1.0), 0.0)


def _step_up_basis(run: _Run, step_up_by_treatment: dict[str, np.ndarray]) -> None:
    """Raise cost bases by income the regime taxed while the holding was still held.

    So selling later does not tax the same euro twice. The regime returns one figure per
    treatment and does not know about accounts, so each figure is spread across that
    treatment's accounts in proportion to the income each earned. Keyed by treatment
    because a regime may charge one treatment on an estimate rather than on reported
    income (a fund that reports nothing): split across every account by reported income,
    that estimate landed on a neighbour that did report, and the fund it was charged on
    was taxed again at sale. Equality on the key only — the engine still does not know
    what any treatment string means (invariant 1 in CONTRIBUTING.md).

    Every account of the treatment takes part, yields or not. Where none of them reported
    income in a run, the year's positive growth carries the split instead.
    """
    ty = run.tax_year
    for treatment, step_up in step_up_by_treatment.items():
        if not np.any(step_up != 0.0):
            continue
        ids = [a.id for a in run.plan.accounts if a.id is not None and a.tax_treatment == treatment]
        deemed = {i: ty.income[i] + ty.fund_gains[i] for i in ids}
        grown = {i: np.maximum(ty.growth[i], 0.0) for i in ids}
        total_deemed = sum(deemed.values(), start=np.zeros(run.n_runs))
        total_grown = sum(grown.values(), start=np.zeros(run.n_runs))
        by_income = total_deemed > 0.0
        by_growth = ~by_income & (total_grown > 0.0)
        for account_id in ids:
            share = np.where(
                by_income,
                deemed[account_id] / np.where(by_income, total_deemed, 1.0),
                np.where(
                    by_growth,
                    grown[account_id] / np.where(by_growth, total_grown, 1.0),
                    0.0,
                ),
            )
            run.basis[account_id] = run.basis[account_id] + step_up * share


def _sweep_cash(run: _Run, when: date, inflation_factor: float, vve_now: float) -> None:
    """Step 8: move money between cash and investments so cash sits inside its buffer."""
    plan, regime = run.plan, run.regime
    sources = sellable_accounts(plan.accounts, when, plan.assumptions.cash_sweep_order)
    sweep_excluded = regime.sweep_excluded_treatments()
    # Wrappers the regime says are bad destinations (locked or penalised) are sellable but
    # never receive surplus cash. This is deliberately NOT the withdrawal-taxed set: under
    # a realization tax every ordinary brokerage account is taxed on the way out and is
    # still exactly where cash belongs. Set membership only — the engine still does not
    # know what any treatment string means.
    moved = apply_sweep(
        run.balances,
        run.cash_id,
        sources,
        buy_targets=[a for a in sources if a.tax_treatment not in sweep_excluded],
        # Once the mortgage is repaid the payment stops leaving cash, so it must stop
        # sizing the buffer too — `payment` is set at purchase and never cleared, and
        # step 6 zeroes only the debit, not the variable.
        target=_buffer_target(
            plan,
            when,
            inflation_factor,
            (run.home.payment if np.any(run.home.mortgage > 0.0) else 0.0) + vve_now,
            flows=run.flows,
        ),
        deadband=plan.assumptions.cash_buffer_deadband,
        # `pro_rata` is a SweepOrder member, not a magic value.
        pro_rata=plan.assumptions.cash_sweep_order == "pro_rata",
    )
    # Neither direction is a gain, so both are flows. Miss this and every sweep
    # manufactures a phantom capital gain or loss, which under the tegenbewijs and the
    # 2028 WWR regime feeds straight into the wealth tax.
    realized_gains: dict[int, np.ndarray] = {}
    for account_id, delta in moved.items():
        if not np.any(delta):
            # Nothing moved: every update below would add zero.
            continue
        if run.accounts_by_id[account_id].tax_treatment in regime.actual_return_treatments():
            run.tax_year.add_inflow(delta)
        realized_gains[account_id] = _apply_basis_move(run.basis, run.balances, account_id, delta)
        run.tax_year.record_sale(account_id, realized_gains[account_id])
    if regime.withdrawal_taxed_treatments():
        _charge_withdrawal_tax(run, when, moved, realized_gains)


def _charge_withdrawal_tax(
    run: _Run, when: date, moved: dict[int, np.ndarray], realized_gains: dict[int, np.ndarray]
) -> None:
    """Tax on what the sweep withdrew this month.

    Charged on the gross sum taken out, so cash nets less than the sale raised and the
    buffer is left short by the tax; the next month's sweep closes the gap. Deliberately
    not grossed up: inverting the charge to sell exactly enough would need the regime to
    be invertible, and the buffer is best-effort anyway.

    Charged on the year's running totals, then netted against what has already been
    charged this year. For a flat rate the result is identical to charging each sale on
    its own; where a regime's charge is not linear in the gain it is not, and that is the
    point — a loss in November reduces the tax on a gain realized in March, which is
    exactly the within-year Verlustausgleich an Austrian depot bank performs. A
    progressive income tax on a payout works the same way: each month pays the rise in
    the tax on the year so far, stacked on the owner's income so far, and
    `_true_up_withdrawal_tax` settles the year against its full income.
    """
    taxed_on_withdrawal = run.regime.withdrawal_taxed_treatments()
    for account_id, delta in moved.items():
        account = run.accounts_by_id[account_id]
        treatment = account.tax_treatment
        if treatment not in taxed_on_withdrawal or not np.any(delta < 0.0):
            continue
        key = (treatment, account.owner_person_id)
        run.tax_year.add_sale(
            key,
            np.maximum(-delta, 0.0),
            realized_gains.get(account_id, np.zeros(run.n_runs)),
        )
        _charge_pool(run, key, when.year)


def _true_up_withdrawal_tax(run: _Run, year: int) -> None:
    """Recharge each of the year's sale pools on the year's final figures.

    Income that arrives after the year's last sale (a December bonus) still lands under
    the payouts, so the year's charges sum to the tax on the whole year. For a charge
    that does not read the owner's income this changes nothing. Pools from before a
    move are left alone: the new regime does not tax their treatment.
    """
    taxed_on_withdrawal = run.regime.withdrawal_taxed_treatments()
    for key in list(run.tax_year.withdrawn):
        if key[0] in taxed_on_withdrawal:
            _charge_pool(run, key, year)


def _charge_pool(run: _Run, key: _SaleKey, year: int) -> None:
    """Charge what the pool's year-to-date tax adds to what it has already been charged."""
    treatment, owner = key
    due = run.regime.withdrawal_tax(
        run.tax_year.withdrawn[key],
        treatment=treatment,
        realized_gain=run.tax_year.realized_gain[key],
        owner_person_id=owner,
        owner_income=run.tax_year.income_of(owner, len(run.plan.people)),
        owner_state_pension_date=None if owner is None else run.state_pension_dates.get(owner),
        year=year,
    )
    charge = run.tax_year.charge_withdrawal(key, due)
    run.balances[run.cash_id] -= charge
    run.tax_paid["withdrawal_tax"][:, run.year_index[year]] += charge
