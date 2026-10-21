"""The value objects the engine consumes. No SQLAlchemy, no session, no I/O.

Everything here is frozen: a projection must not be able to mutate its own inputs.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountKind(StrEnum):
    """Economic nature. Country-neutral. The ENGINE reads this.

    DEBT-kind account balances are stored NEGATIVE (the amount owed, signed): a
    EUR50,000 loan is ``manual_value = Decimal("-50000")``. Net worth sums the
    components, so debt must carry its own sign.
    """

    CASH = "cash"
    EQUITY = "equity"
    BOND = "bond"
    REAL_ESTATE = "real_estate"
    PENSION = "pension"
    DEBT = "debt"


def check_balance_sign(name: str, kind: AccountKind, manual_value: Decimal | None) -> None:
    """Refuse a balance with the wrong sign: DEBT is stored negative, every other kind not.

    The one rule the API's account create/update, the import and the seed all apply. A
    positive debt fails the Dutch Box 3 base and adds to net worth everywhere else; a
    negative asset is silently clamped out of the Box 3 base.
    """
    if manual_value is None:
        return
    if kind is AccountKind.DEBT and manual_value > 0:
        msg = (
            f"DEBT account {name!r} has a positive manual_value ({manual_value}): debts are "
            "stored negative, the amount owed with its sign"
        )
        raise ValueError(msg)
    if kind is not AccountKind.DEBT and manual_value < 0:
        msg = (
            f"account {name!r} has a negative manual_value ({manual_value}): only DEBT "
            "accounts are stored negative"
        )
        raise ValueError(msg)


class PriceSource(StrEnum):
    """Where an account's unit price comes from."""

    STOOQ = "stooq"
    MANUAL = "manual"


# The currencies an account may be *quoted* in. Reporting is always EUR
# (`Household.base_currency`); this is only what a price fetch has to convert from, so
# every member needs an ECB daily reference rate. Widen it when a holding needs one.
# NOTE: a plain Literal, not an ISO-4217 type — validating all ~300 codes would
# accept currencies the price layer cannot convert.
Currency = Literal["EUR", "USD"]


class CashFlowKind(StrEnum):
    """What a recurring monthly flow does: earn, spend, or invest."""

    INCOME = "income"
    EXPENSE = "expense"
    CONTRIBUTION = "contribution"


class _Frozen(BaseModel):
    # A field with a default is always present in a response, so the response schema
    # marks it required and the generated frontend types do not make it optional.
    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)


# --- milestone params ---


class BuyProperty(_Frozen):
    """Milestone params: buy a home, funded by an annuity mortgage."""

    type: Literal["buy_property"] = "buy_property"
    price: Decimal
    mortgage: Decimal
    annual_rate: Decimal
    term_months: int = 360
    vve_monthly: Decimal = Decimal(0)
    buyer_person_id: int | None = None
    gift_used: Decimal = Decimal(0)
    own_occupancy: bool = True


class ExtraRepayment(_Frozen):
    """Milestone params: pay `monthly_amount` extra into the mortgage, every month.

    The aflossen half of aflossen-vs-beleggen. It runs from the milestone
    date until the mortgage is gone; the annuity payment is *not* recalculated, so the
    term shortens rather than the monthly payment dropping — "looptijd verkorten", not
    "maandlast verlagen". The other choice is not modelled: re-amortising would lower the
    payment and save less interest, so this models the variant that favours repaying.
    """

    type: Literal["extra_repayment"] = "extra_repayment"
    monthly_amount: Decimal


class SellProperty(_Frozen):
    """Milestone params: sell the home, netting `costs` off the proceeds."""

    type: Literal["sell_property"] = "sell_property"
    costs: Decimal = Decimal(0)


class IncomeChange(_Frozen):
    """Milestone params: reset an income cash flow's monthly amount."""

    type: Literal["income_change"] = "income_change"
    cash_flow_id: int
    new_amount_monthly: Decimal


class ExpenseChange(_Frozen):
    """Milestone params: reset an expense cash flow's monthly amount."""

    type: Literal["expense_change"] = "expense_change"
    cash_flow_id: int
    new_amount_monthly: Decimal


class LumpSumIn(_Frozen):
    """Milestone params: a one-off inflow — inheritance, bonus, or a parental gift."""

    type: Literal["lump_sum_in"] = "lump_sum_in"
    amount: Decimal
    target_account_id: int | None = None
    is_gift_exemption: bool = False


class LumpSumOut(_Frozen):
    """Milestone params: a one-off outflow."""

    type: Literal["lump_sum_out"] = "lump_sum_out"
    amount: Decimal


class Retire(_Frozen):
    """Milestone params: a person stops working."""

    type: Literal["retire"] = "retire"
    person_id: int


class ContributionChange(_Frozen):
    """Milestone params: reset a recurring contribution's monthly amount."""

    type: Literal["contribution_change"] = "contribution_change"
    cash_flow_id: int
    new_amount_monthly: Decimal


class ChangeTaxResidence(_Frozen):
    """A move to another country. Swaps the active TaxRegime mid-projection."""

    type: Literal["change_tax_residence"] = "change_tax_residence"
    country: str
    retag: dict[int, str] = {}
    """The new `tax_treatment` per account id, applied in the month of the move.

    A treatment is scoped to its country, so after the move every account must carry
    one the new regime knows. A plan that leaves any account on a key the new regime
    does not know is refused: that account would otherwise be taxed as nothing.
    """


MilestoneParams = Annotated[
    BuyProperty
    | ExtraRepayment
    | SellProperty
    | IncomeChange
    | ExpenseChange
    | LumpSumIn
    | LumpSumOut
    | Retire
    | ContributionChange
    | ChangeTaxResidence,
    Field(discriminator="type"),
]


TaxOverrides = dict[str, dict[int, dict[str, Decimal]]]
"""Per-scenario tax-figure overrides: country -> year -> {config field: value}."""


class ScenarioOverrides(_Frozen):
    """A scenario's deviations from the stored plan.

    Only `tax` is read by the engine (`project()`); the caller applies the rest when
    building the `PlanInput` it hands to the engine.
    """

    accounts: dict[int, dict[str, object]] = {}
    cash_flows: dict[int, dict[str, object]] = {}
    milestones: dict[int, dict[str, object] | None] = {}
    added_milestones: list[dict[str, object]] = []
    household: dict[str, object] = {}
    # `object`, not `Decimal`: the cash-buffer assumptions include two Literal strings
    # (mode, sweep order) and a bool. Matches `accounts` and `household` above.
    assumptions: dict[str, object] = {}
    tax: TaxOverrides = {}


# --- entities ---


class Household(_Frozen):
    """The unit every other row hangs off, and the owner of the tax country."""

    id: int
    name: str
    base_currency: Literal["EUR"] = "EUR"
    tax_country: str = "NL"
    fiscal_partners: bool = False
    life_expectancy_age: int = 95


FilingStatus = Literal["single", "married_filing_separately", "married_filing_jointly"]
"""How a US person files. Three values, because only three change the arithmetic.

Married filing separately is the expatriate norm: electing to file jointly drags a
non-resident-alien spouse onto the US return. It is an input rather than an assumption
because it is a decision a real filer makes, and the app should price it rather than
presume it. Head of household is deliberately absent — it needs a qualifying dependent
and a maintained household, neither of which the domain models.
"""


class Person(_Frozen):
    """A household member. `birth_date` drives AOW age and age-triggered milestones."""

    id: int
    household_id: int
    name: str
    birth_date: date = date(1990, 1, 1)
    tax_residence: str = "NL"
    pension_age_override: str | None = None
    us_person: bool = False
    """Whether US citizenship-based taxation reaches this person.

    Named for the tax concept rather than `citizenship`, because green-card holders are
    US persons too. A boolean rather than a list of citizenships because the United
    States is the only country that broadly taxes by citizenship — every other
    expatriate is taxed by residence alone, and a foreign holding is one regime plus a
    withholding leak. A tax input and nothing else.
    """

    us_filing_status: FilingStatus | None = None
    """Only meaningful when `us_person`. `None` means not recorded."""


class Account(_Frozen):
    """One asset or debt position.

    `kind` is the country-neutral economic nature the engine reads; `tax_treatment` is
    the country-scoped key only the regime interprets. DEBT balances are negative.
    """

    id: int
    household_id: int
    name: str
    kind: AccountKind
    tax_treatment: str
    overlay_treatment: str | None = None
    """The citizenship overlay's classification, as `tax_treatment` is the residence
    regime's.

    Third of three orthogonal classifications, and the seam depends on them staying
    orthogonal: `kind` is country-neutral economic nature for the engine,
    `tax_treatment` is residence-scoped (`nl.box3_investment`), and this is
    citizenship-scoped (`us.non_pfic`). The US overlay must never read an `nl.*` key,
    and NL must never read a `us.*` one.

    `None` means no overlay applies to this account, which is every account in a
    household with no US person.
    """

    owner_person_id: int | None = None
    isin: str | None = None
    price_source: PriceSource = PriceSource.MANUAL
    # Quote currency, for the price layer only. The engine reads EUR values throughout.
    currency: Currency = "EUR"
    units: Decimal | None = None
    manual_value: Decimal | None = None
    cost_basis: Decimal | None = None
    return_assumption: float = 0.0
    volatility_assumption: float = 0.0
    # Annual fund cost (TER), a drag on gross return. Nominal like `return_assumption`,
    # so the engine deducts `expense_ratio / 12` a month.
    expense_ratio: float = 0.0
    distribution_yield: float = 0.0
    """The share of this holding's value that arrives each year as ordinary income —
    dividends, coupons or bank interest — rather than as price appreciation.

    A *decomposition* of `return_assumption`, not an addition to it: the balance still
    grows by the total return, and this only says how much of that growth the tax
    authorities see as income. An accumulating fund reinvests it and the balance is
    unaffected, which is exactly the case that matters, because several countries tax
    that income anyway.

    Zero by default, which means "no income component modelled" and leaves every
    projection that predates this field unchanged. A world equity ETF is around 0.018.
    """
    fund_realized_gain_yield: float = 0.0
    """The share of this holding's value that the *fund itself* realises as capital gains
    each year by trading its own portfolio.

    Nothing to do with the holder selling: this is turnover inside the wrapper, which
    some countries pass through and tax annually even though the holder did nothing
    (Austria deems 60% of it distributed). Distinct from `distribution_yield`, which is
    dividends and interest, because the two are taxed on different fractions.

    Zero by default, which is close to true for a physically replicating index ETF —
    in-kind creation and redemption means it rarely realises anything. An actively
    managed fund is materially above zero.
    """
    liquid_from: date | None = None


class CashFlow(_Frozen):
    """A recurring monthly income, expense or contribution."""

    id: int
    household_id: int
    label: str
    amount_monthly: Decimal
    kind: CashFlowKind
    owner_person_id: int | None = None
    target_account_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    inflation_linked: bool = True


class Milestone(_Frozen):
    """A one-off event that changes the plan, fired on a date or at a person's age."""

    id: int
    household_id: int
    label: str
    params: MilestoneParams
    on_date: date | None = None
    age_person_id: int | None = None
    age_years: int | None = None


class Scenario(_Frozen):
    """A named what-if: the stored plan plus a set of overrides."""

    id: int
    household_id: int
    name: str
    is_baseline: bool = False
    overrides: ScenarioOverrides = ScenarioOverrides()
