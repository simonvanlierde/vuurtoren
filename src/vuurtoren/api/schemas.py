"""Request and response schemas.

Read models are the frozen `domain` value objects returned by each row's `to_domain()`
— Decimal fields serialise as strings there already, so no separate "Out" schema is
needed except for PricePoint, which has no domain equivalent (the plan reads only its
latest `value_eur`, folded into `Account.manual_value`), and the compute endpoints,
whose numpy results are typed at the bottom of this file so the frontend can generate
its types from them.

Write models validate on the way in. `Milestone.params` and `Scenario.overrides` are
typed as the domain discriminated unions directly, so a typo'd milestone type or a stray
override field fails FastAPI's request validation with 422 before it ever reaches the
database.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    PastDate,
    field_validator,
    model_validator,
)

from vuurtoren import domain
from vuurtoren.tax.config import check_tax_overrides
from vuurtoren.tax.regime import registered_countries


class HouseholdIn(BaseModel):
    """Request body for a household."""

    name: str = "Household"
    base_currency: Literal["EUR"] = "EUR"
    tax_country: str = "NL"
    fiscal_partners: bool = False
    life_expectancy_age: int = 95

    @field_validator("tax_country")
    @classmethod
    def _known_country(cls, value: str) -> str:
        # Saved unchecked, an unknown country broke every projection with a 500.
        if value not in registered_countries():
            msg = f"no tax regime for {value!r}; choose one of {registered_countries()}"
            raise ValueError(msg)
        return value


class PersonIn(BaseModel):
    """Request body for a person in the household."""

    household_id: int
    name: str
    birth_date: PastDate
    tax_residence: str = "NL"
    pension_age_override: str | None = None
    us_person: bool = False
    us_filing_status: domain.FilingStatus | None = None


class AccountIn(BaseModel):
    """Request body for an account."""

    household_id: int
    owner_person_id: int | None = None
    name: str = ""
    kind: domain.AccountKind = domain.AccountKind.CASH
    # Required, no default. `""` is not a treatment any regime lists, so defaulting it
    # turned "the client forgot the field" into the regime's complaint about a value
    # nobody sent; pydantic names the field instead.
    tax_treatment: str
    overlay_treatment: str | None = None
    isin: str | None = None
    price_source: domain.PriceSource = domain.PriceSource.MANUAL
    currency: domain.Currency = "EUR"
    units: Decimal | None = None
    manual_value: Decimal | None = None
    cost_basis: Decimal | None = None
    return_assumption: float = 0.0
    volatility_assumption: float = 0.0
    expense_ratio: float = 0.0
    distribution_yield: float = 0.0
    fund_realized_gain_yield: float = 0.0
    liquid_from: date | None = None

    @model_validator(mode="after")
    def _valid(self) -> AccountIn:
        _check_account(self)
        return self


class CashFlowIn(BaseModel):
    """Request body for a recurring cash flow."""

    household_id: int
    owner_person_id: int | None = None
    label: str = ""
    amount_monthly: Decimal = Decimal(0)
    kind: domain.CashFlowKind = domain.CashFlowKind.EXPENSE
    target_account_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    inflation_linked: bool = True

    @model_validator(mode="after")
    def _valid(self) -> CashFlowIn:
        _check_cash_flow(self)
        return self


def _check_account(a: AccountIn | domain.Account) -> None:
    """The account rules every way in shares: create, update and import."""
    domain.check_balance_sign(a.name, a.kind, a.manual_value)
    if a.kind is domain.AccountKind.PENSION and a.owner_person_id is None and a.liquid_from is None:
        # The unlock date derives from the owner's state-pension age; with neither, the
        # engine would count the pot as liquid from the first month.
        msg = f"PENSION account {a.name!r} needs an owner or a liquid_from date"
        raise ValueError(msg)


def _check_cash_flow(f: CashFlowIn | domain.CashFlow) -> None:
    """The cash-flow rule create, update and import share."""
    if f.kind is domain.CashFlowKind.CONTRIBUTION and f.target_account_id is None:
        # Without a target the contribution leaves cash and arrives nowhere.
        msg = f"CONTRIBUTION {f.label!r} needs a target_account_id"
        raise ValueError(msg)


class MilestoneIn(BaseModel):
    """Request body for a milestone; `params` is the domain discriminated union."""

    household_id: int
    label: str = ""
    on_date: date | None = None
    age_person_id: int | None = None
    age_years: int | None = None
    params: domain.MilestoneParams


class ScenarioIn(BaseModel):
    """Request body for a scenario and its override groups."""

    household_id: int
    name: str = ""
    is_baseline: bool = False
    overrides: domain.ScenarioOverrides = domain.ScenarioOverrides()

    @model_validator(mode="after")
    def _known_tax_fields(self) -> ScenarioIn:
        check_tax_overrides(self.overrides.tax)
        return self


class PricePointIn(BaseModel):
    """Request body for a price point."""

    account_id: int
    date: date
    price_native: Decimal
    currency: domain.Currency
    fx_rate_to_eur: Decimal
    value_eur: Decimal
    source: str


class PricePointOut(PricePointIn):
    """A stored price point, read back with its row id."""

    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )
    id: int


class ManualPriceIn(BaseModel):
    """Request body for /api/price-points/manual: the server does the FX."""

    account_id: int
    date: date
    price: Decimal | None = None
    value: Decimal | None = None


class AssumptionsIn(BaseModel):
    """Economy-wide assumptions for one projection run."""

    inflation: float = 0.02
    swr: float = 0.04
    coast_return: float = 0.06
    house_appreciation: float = 0.02
    state_pension_growth_months_per_decade: int = Field(
        3,
        validation_alias=AliasChoices(
            "state_pension_growth_months_per_decade", "aow_growth_months_per_decade"
        ),
    )
    """Months the state pension age drifts later per decade of birth year.

    The old `aow_growth_months_per_decade` still validates: stored scenarios and any
    client written against the previous name keep working. See `Assumptions`."""
    index_tax_allowances: bool = True
    usd_to_eur: Decimal = Decimal("0.851")
    """Euros per dollar, the assumed yearly average — the rate the IRS mandates for
    translating income and creditable foreign taxes. Only a household with a US person
    reads it. See `Assumptions.usd_to_eur`."""


_MAX_PROJECT_RUNS = 10_000
"""Each run is a full (n_months,) series per account; past this a request is a memory
problem, not a sharper fan chart."""


class PlanRequestBase(BaseModel):
    """The fields every request that names a plan carries.

    `scenario_id` and `overrides` are mutually exclusive: one names a stored scenario,
    the other is an unsaved one (a drawer preview, live tax edits in `overrides.tax`).
    An unknown field is a 422, not ignored: a misspelt or retired field would otherwise
    run a different plan than the caller meant.
    """

    model_config = ConfigDict(extra="forbid")

    household_id: int | None = None
    """None picks the sole household — there is exactly one in v1."""
    scenario_id: int | None = None
    start: date
    assumptions: AssumptionsIn = AssumptionsIn()
    overrides: domain.ScenarioOverrides | None = None
    """Inline scenario overrides, applied through `apply_scenario` and never persisted."""


class ProjectRequest(PlanRequestBase):
    """Request body for /api/project."""

    n_runs: int = Field(1, ge=1, le=_MAX_PROJECT_RUNS)
    seed: int | None = None
    """Monte Carlo seed. None with n_runs > 1 gets one assigned and echoed back."""
    mode: Literal["gaussian", "historical", "sequential"] = "gaussian"
    """Returns model for n_runs > 1. "gaussian" draws per-month shocks from
    the account assumptions; "historical" bootstraps blocks of real global-equity years;
    "sequential" runs each real start year as its own path, so a run has a
    calendar name. Ignored at n_runs == 1 — the deterministic path uses
    fixed returns — and "historical" there is rejected rather than silently ignored.
    "sequential" ignores `n_runs` and `seed` entirely: the dataset fixes the run count
    and there is no rng to seed. Both are echoed back as what actually ran."""
    min_end_net_worth: float | None = None
    """Bequest floor / die-with-zero: a run counts as a success only if it ends with at
    least this much net worth. None keeps plain solvency. Monte Carlo only — it shapes
    `success_probability`, which the deterministic run does not report."""


class SolveGoal(BaseModel):
    """The target /api/solve bisects toward. Fields used depend on `type`."""

    type: Literal["fire_by", "net_worth_at", "success_at_least"]
    year: int | None = None
    """fire_by / net_worth_at: reach the goal on or before December of this year."""
    at_least: float | None = None
    """net_worth_at: the end-year net worth to land on. 0 is die-with-zero."""
    probability: float | None = None
    """success_at_least: the Monte Carlo solvency fraction to hold."""
    n_runs: int = Field(1000, ge=1)
    """success_at_least: Monte Carlo runs per bisection step (capped server-side)."""
    min_end_net_worth: float | None = None
    """success_at_least: the bequest floor, as on `ProjectRequest`. None keeps plain
    solvency."""


class SolveRequest(PlanRequestBase):
    """Request body for /api/solve — the plan-assembly half of ProjectRequest plus a knob.

    Carries the knob to bisect and the goal to hit. No n_runs/seed/mode here: the
    deterministic goals run at n_runs=1 and success_at_least carries its own n_runs.
    """

    knob: Literal["monthly_spending", "monthly_contributions"]
    goal: SolveGoal


class RetirementRequest(PlanRequestBase):
    """Request body for /api/retirement — early retirement, both directions.

    Exactly one of `at_date` / `probability`: the first reports the odds for a date the
    user names, the second solves for the earliest date clearing a probability they name.
    Sending both is a caller error rather than a silently-picked default.

    Shaped like `SolveRequest` rather than `ProjectRequest`: `mode` and
    `min_end_net_worth` mean nothing here, and the run count is the only knob wanted.
    """

    person_ids: list[int]
    """Whose income stops. One id solves one person's date; several solve a shared one —
    "retire together" is a longer list, not a second mode."""
    residual_monthly: Decimal = Decimal(0)
    """What the named people still earn afterwards. 0 is full retirement; a positive
    figure is baristaFIRE. The UI's %-of-salary / %-of-expenses toggles resolve to this
    absolute amount before sending, so the server has no opinion about which produced it."""
    at_date: date | None = None
    probability: float | None = None
    n_runs: int = Field(1000, ge=1)


class SensitivityRequest(PlanRequestBase):
    """Request body for /api/sensitivity — the plan-assembly half plus the metric to rank on.

    No knob: the tornado moves every assumption it can, which is the point of it. No
    n_runs/seed either — it is the deterministic path throughout.
    """

    metric: Literal["fi_year", "end_net_worth"] = "fi_year"


class SweepRequest(PlanRequestBase):
    """Request body for /api/sweep — like SolveRequest but a whole curve, not one answer."""

    knob: Literal["monthly_spending", "monthly_contributions"]
    points: int = 25
    n_runs: int = Field(500, ge=1)


class FbarRequest(ProjectRequest):
    """A projection request plus the reporting year to read off it.

    Subclasses `ProjectRequest` rather than repeating it: the worksheet is a *reading* of
    a projection, so it must be built from the same plan, the same assumptions and the
    same start date the user is looking at. Monte Carlo fields are inherited and ignored —
    a filing obligation is not a distribution, so run 0 is what gets read.
    """

    year: int
    usd_per_eur_override: Decimal | None = Field(default=None, gt=0)
    """Skip the Treasury fetch and use this rate instead — `exchange_rate` as Treasury
    publishes it, foreign currency per one US dollar. For a year Treasury has not published
    yet, which every projected year is."""


class ImportDocument(BaseModel):
    """An export document read back for import.

    Each section is typed as the same model the export dumped, so a malformed document
    fails FastAPI validation with 422 before a single row is written.
    """

    version: int
    household: domain.Household
    people: list[domain.Person] = []
    accounts: list[domain.Account] = []
    price_points: list[PricePointOut] = []
    cash_flows: list[domain.CashFlow] = []
    milestones: list[domain.Milestone] = []
    scenarios: list[domain.Scenario] = []

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_milestones(cls, data: object) -> object:
        # v0.1.0 wrote an empty `milestones` group into every scenario's overrides, a
        # group it never applied. Drop it so those exports still import; a non-empty one
        # is left for `ScenarioOverrides` to refuse as an unknown key.
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        for s in scenarios if isinstance(scenarios, list) else []:
            overrides = s.get("overrides") if isinstance(s, dict) else None
            if isinstance(overrides, dict) and overrides.get("milestones") == {}:
                del overrides["milestones"]
        return data

    @model_validator(mode="after")
    def _valid(self) -> ImportDocument:
        # Import writes straight to the tables, so it applies the create rules itself.
        for a in self.accounts:
            _check_account(a)
        for f in self.cash_flows:
            _check_cash_flow(f)
        return self


# --- compute responses ---
# Field order is the JSON key order, so it must match what the endpoints return.


class FlowTotalsOut(BaseModel):
    """Monthly flow totals, run-independent. Index 0 is the opening position."""

    income: list[float]
    expenses: list[float]
    contributions: list[float]
    housing: list[float]


class FireOut(BaseModel):
    """The deterministic projection's FI/FIRE figures. Every list is per run."""

    fire_number: float
    fi_dates: list[date | None]
    """None = that run never reached FI."""
    coast_fire_dates: list[date | None]
    savings_rate: float
    fire_usable: list[list[float]]
    """(n_runs, n_months)."""
    net_swr: float
    """Gross SWR minus the Box 3 drag on the investment portfolio: "4% after Box 3"."""


class ProjectionOut(BaseModel):
    """/api/project at n_runs=1.

    `net_worth`, `components` and `investment_income` are (n_runs, n_months) matrices even
    at n_runs=1, so every reader slices run 0 itself.
    """

    months: list[date]
    inflation_factor: list[float]
    """Cumulative price level per month, 1.0 at the start: the real-terms deflator."""
    flow_totals: FlowTotalsOut
    net_worth: list[list[float]]
    components: dict[str, list[list[float]]]
    tax_paid: dict[str, list[list[float]]]
    """Per tax year, (n_runs, n_years): investment_tax, housing_adjustment, withdrawal_tax."""
    one_off_costs: dict[str, list[float]]
    """Per run: transfer_tax."""
    investment_income: list[list[float]]
    fire: FireOut
    cash_shortfall: list[date | None]
    """Per run, the month cash first went negative; None if it never did."""


class BandsOut(BaseModel):
    """Net-worth percentiles per month across the runs."""

    p10: list[float]
    p50: list[float]
    p90: list[float]


class MonteCarloFireOut(BaseModel):
    """The Monte Carlo FI figures. `fi_dates` is per run and drives the FIRE-date histogram."""

    fire_number: float
    savings_rate: float
    fi_dates: list[date | None]
    net_swr: float


class MonteCarloOut(BaseModel):
    """/api/project at n_runs > 1: percentile bands, not n_runs x n_months of JSON."""

    months: list[date]
    inflation_factor: list[float]
    n_runs: int
    seed: int | None
    """None in sequential mode, which has no rng to seed."""
    mode: Literal["gaussian", "historical", "sequential"]
    start_years: list[int] | None
    """Sequential mode only: run r is start year start_years[r]."""
    bands: BandsOut
    success_probability: float
    solvent_fraction: list[float]
    """Fraction of runs still solvent at each month."""
    survival: list[float]
    """P(at least one person alive) per month, from the CBS life table."""
    flow_totals: FlowTotalsOut
    fire: MonteCarloFireOut


class SolveOut(BaseModel):
    """/api/solve. `solved_monthly` is None when the goal has no solution in range."""

    knob: Literal["monthly_spending", "monthly_contributions"]
    baseline_monthly: float
    solved_monthly: float | None
    achieved: float | None
    converged: bool


class RetirementOut(BaseModel):
    """/api/retirement. `fi_date` is the 4%-rule date from the same run, shown beside it."""

    retire_date: date | None
    achieved: float | None
    fi_date: date | None
    converged: bool


class SweepPointOut(BaseModel):
    """One knob level on the spending-vs-success curve."""

    monthly: float
    success: float
    end_worth: float


class SweepOut(BaseModel):
    """/api/sweep."""

    knob: Literal["monthly_spending", "monthly_contributions"]
    baseline_monthly: float
    points: list[SweepPointOut]


class SensitivityRowOut(BaseModel):
    """One tornado bar. `low`/`high` are None when FI is not reached that way."""

    knob: Literal["return_assumption", "inflation", "swr", "house_appreciation"]
    delta: float
    low: float | None
    high: float | None


class SensitivityOut(BaseModel):
    """/api/sensitivity. `baseline` is None for an FI year the baseline never reaches."""

    metric: Literal["fi_year", "end_net_worth"]
    baseline: float | None
    rows: list[SensitivityRowOut]
