"""The country seam.

engine.py imports this module and nothing under tax/<country>/. One protocol, two
implementations (NL and AT). No registry, no plugin discovery, no rules DSL — adding a
country means writing tax/<cc>/ and adding one dict entry below.

The two countries are shaped differently on purpose, and that is what keeps this honest:
NL taxes holdings annually, AT taxes income while held and the gain at sale. Several
methods here exist as separate concepts only because AT proved they were separate —
`sweep_excluded_treatments` apart from `withdrawal_taxed_treatments`, and
`annual_basis_step_up` so income taxed while held is not taxed again on sale.

The recurring annual/monthly methods work in `(n_runs,)` float64 arrays: the
engine is vectorised throughout, and scalar signatures forced a Python loop over runs at
every call site — at n_runs=10_000 that loop was the entire Monte Carlo budget. The
one-off, run-independent methods (`purchase_costs`, `state_pension_date`) stay scalar:
they fire at most a handful of times per projection, and `Decimal` is the API-boundary
type for money that reaches the user.

`actual_return_treatments()` and `YearState.investment_gain` are NL-only seam members for
the tegenbewijs election: a regime with no counter-evidence rule can return an
empty `frozenset` and leave `investment_gain` `None` — that is a correct "not applicable,"
not a gap to fill.
"""

from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

# Runtime import, not TYPE_CHECKING: TaxConfigBase is the bound of the protocol's type
# parameter. tax/config.py imports nothing from here, so there is no cycle.
from vuurtoren.tax.config import TaxConfigBase

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    import numpy as np

    from vuurtoren.tax.overlay import PersonSlice, TreatmentMaps


@dataclass(frozen=True)
class YearState:
    """The household's position at a year boundary, in country-neutral terms.

    A regime reads the fields it cares about and ignores the rest. Every per-run field
    is an `(n_runs,)` float64 array; a regime must return the same shape and must not
    mutate what it is handed.
    """

    year: int
    balances_by_treatment: dict[str, np.ndarray]
    home_value: np.ndarray
    mortgage_interest_paid: np.ndarray
    fiscal_partners: bool
    income_by_treatment: dict[str, np.ndarray] = field(default_factory=dict)
    """Ordinary income earned this year, per tax_treatment.

    Dividends, coupons and bank interest — the part of a holding's return that is income
    rather than price appreciation, derived from each account's `distribution_yield`. It
    is earned whether or not it was paid out, which is the case that matters: an
    accumulating fund reinvests it and several countries tax it regardless (Austria's
    ausschuettungsgleiche Ertraege).

    Keyed by treatment, like `balances_by_treatment`, because the rate can differ by
    wrapper — Austria charges 25% on bank interest against 27.5% on securities.

    Distinct from `investment_gain`, which is the whole year-on-year value change and so
    *includes* this. A regime that taxes both must not add them together.
    """

    fund_realized_gains_by_treatment: dict[str, np.ndarray] = field(default_factory=dict)
    """Gains the *funds themselves* realised this year by trading, per tax_treatment.

    Derived from each account's `fund_realized_gain_yield`. Separate from
    `income_by_treatment` because a country can tax the two on different fractions —
    Austria deems 100% of a fund's income distributed but only 60% of its realised gains.
    """

    value_growth_by_treatment: dict[str, np.ndarray] = field(default_factory=dict)
    """The year's change in value from returns alone, per tax_treatment.

    Deposits and withdrawals are excluded, so this is the change a unit price would show
    rather than the change in what the holder has put in. That is the base a lump-sum
    regime needs: Austria taxes a non-reporting fund on
    `max(90% of the year's rise, 10% of the year-end value)`, and counting a
    contribution as a rise would tax the holder for saving.
    """

    by_person: dict[int, PersonSlice] = field(default_factory=dict)
    """Each person's share of the year, for a citizenship overlay.

    Empty for every residence regime, which is all of them: NL and AT tax a household,
    not a citizen. Populated by the engine because only the engine knows who owns which
    account.

    Carries plain ownership facts and stops there — what a person owns outright and what
    the household owns jointly, kept apart. Deciding how much of a joint holding falls
    inside another country's net is that country's rule, so the overlay applies it and
    invariant #1 keeps it out of `engine.py`.
    """

    by_owner: dict[int | None, TreatmentMaps] = field(default_factory=dict)
    """Each owner's accounts, keyed by `tax_treatment` like `balances_by_treatment`.

    The residence-side twin of `by_person`, for a regime that taxes people who are not
    fiscal partners one by one. Keyed by person id, with `None` for jointly held
    accounts; every person has an entry even when they own nothing, so a regime can
    count them. The engine records ownership only — how a joint account is shared out is
    the regime's rule. Empty means ownership is unknown, and the household is taxed as
    one.
    """

    investment_gain: np.ndarray | None = None
    """Value change over the year across taxable investments — the actual-return input.

    `None` means no actual-return figure is available, so no tegenbewijs election is
    possible (regime A falls back to the forfaitair calculation; regime B cannot be
    computed at all). An array means the caller computed the year's actual return and
    election is allowed — including a run at exactly 0.0, a proven flat year, which is
    not the same thing as an absent figure.
    """

    residence_carry: Any = None
    """What the residence regime's `next_carry` returned for the previous year, or None
    before the first one. Opaque outside that regime: `HouseholdTax` sets it, and the
    engine never builds or reads it (invariant #1)."""


@dataclass(frozen=True)
class Limitation:
    """One thing a regime does not model, and which way that bends the answer.

    Every regime already carries this list in its module docstring, written for whoever
    edits the module. This is the same list written for whoever reads the *result* — the
    engineering record stays where it is and goes deeper; these are the three or four
    lines a user needs to judge a projection they are looking at, in both locales.

    `direction` is the honest part and the reason a bare sentence is not enough: a reader
    who knows the model omits something still cannot tell whether it flatters them.
    """

    direction: Literal["understates", "overstates", "either"]
    """Whether the omission makes the projection look better, worse, or could do either.

    From the *household's* point of view, not the tax authority's: `understates` means the
    plan reads better than reality — tax that is not charged, income that is not reduced.
    """

    nl: str
    en: str


@runtime_checkable
class TaxRegime[ConfigT: TaxConfigBase](Protocol):
    """The seam between the engine and a country's tax rules.

    The engine holds one of these and never looks inside it, so a country is added by
    writing an implementation and one registry entry in `regime_for` — nothing in
    `engine.py` changes.

    Parameterised by the country's config class, so `NLTaxRegime` reads `NLTaxConfig`'s
    fields with the type checker's help while the engine holds a `TaxRegime[Any]` and
    stays country-neutral. Pairing a regime with its config is `regime_for` and
    `resolve_tax_config` being called with the same country code — a runtime fact the
    type parameter documents but cannot enforce.
    """

    @property
    def country(self) -> str:
        """ISO 3166-1 alpha-2 code. Read-only: a regime's country is a fact about it.

        A property rather than an attribute so an implementation may derive it —
        `HouseholdTax` takes its country from the residence regime it wraps — while a
        plain `country = "NL"` class attribute satisfies it just as well.
        """
        ...

    @property
    def limitations(self) -> tuple[Limitation, ...]:
        """What this regime does not model, for the surface where the result is read.

        Part of the seam on purpose. A country's simplifications are the country's own
        fact, and the alternative — a list in the frontend — would be a second copy of
        something only the regime knows, drifting from the module that makes each
        omission. Empty is a legitimate answer; a wrong list is not.
        """
        ...

    def annual_investment_tax(self, s: YearState, cfg: ConfigT) -> np.ndarray:
        """Tax charged annually on investments held, per run. Zero where none exists.

        Deliberately not called `annual_wealth_tax`: a holding tax is only one of the
        shapes this takes. NL charges Box 3 on the wealth itself; Austria has no wealth
        tax at all, yet taxes a fund's ausschuettungsgleiche Ertraege every year on
        holdings that were never sold. Both are "tax that falls due each year on what is
        held", which is the concept the engine actually needs.

        Reads last year's state from `s.residence_carry`; `next_carry` gives this year's.
        """
        ...

    def next_carry(self, s: YearState, cfg: ConfigT) -> Any:  # noqa: ANN401  # opaque per regime
        """The per-run state `annual_investment_tax` needs next year, such as a loss pool.

        None for a regime with no cross-year state. `HouseholdTax.close_year` stores it
        and hands it back as the next year's `s.residence_carry`, the same way an overlay's
        carry travels; a change of residence drops it.
        """
        ...

    def annual_housing_adjustment(self, s: YearState, cfg: ConfigT) -> np.ndarray:
        """Net effect of owning a home: deductions minus imputed income. May be negative."""
        ...

    def purchase_costs(
        self,
        price: Decimal,
        *,
        buyer_age: int,
        own_occupancy: bool = True,
        starter_exemption_used: bool,
        mortgage_amount: Decimal,
        cfg: ConfigT,
    ) -> tuple[Decimal, bool]:
        """One-off transaction taxes at purchase.

        `mortgage_amount` is the sum secured against the property, which is a different
        base from `price`: Austria's Pfandrechtseintragungsgebuehr is 1.2% of the debt
        registered, not of what was paid. A regime whose purchase taxes depend only on
        the price ignores it.

        Returns `(costs, starter_exemption_consumed)`. `starter_exemption_consumed` is
        whether this purchase actually used the single-use starter exemption; the caller
        folds it into its projection state. A purchase that does not qualify (over-age,
        over the value cap, or not own-occupancy) must return `False` so the exemption
        stays available for a later qualifying purchase.

        `own_occupancy` is owned by the caller, not the regime: whether the buyer will
        live in the property as their primary residence is a property of the purchase,
        not of the tax regime itself.

        `starter_exemption_used` is owned by the caller, not the regime: it is
        projection state (whether an earlier milestone already consumed the starter
        exemption), not a fact about the tax regime itself.
        """
        ...

    def state_pension_date(self, birth_date: date, *, growth: int) -> date:
        """When state pension starts, given a growth assumption past the legislated schedule.

        `growth` extrapolates a schedule that a country legislates as tracking life
        expectancy; a regime whose statutory age is flat ignores it.
        """
        ...

    def gift_tax_free_amount(
        self,
        amount: Decimal,
        *,
        recipient_birth_date: date,
        gift_date: date,
        onetime_used: bool,
        cfg: ConfigT,
    ) -> Decimal:
        """The tax-free portion of a parental gift of `amount`.

        One-off and run-independent, so scalar like `purchase_costs`.

        The engine fails loudly when a flagged gift exceeds this — gift tax on the
        excess is deliberately not modelled (gifts are modelled inside the
        exemption only).
        """
        ...

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        year: int,
        cfg: ConfigT,
    ) -> np.ndarray:
        """Tax due on taking `amount` (per run) out of an account with this `tax_treatment`.

        Zero for treatments a withdrawal does not touch — under NL, taking money out of
        a Box 3 investment is not a taxable event at all, but a lijfrente uitkering is
        Box 1 income. The engine calls this whenever it liquidates capital and never
        interprets `treatment` itself.

        `amount` is the gross sum withdrawn; the caller nets the tax off the proceeds.
        A run that withdrew nothing (or deposited) is charged zero.

        `realized_gain` is the part of `amount` that is profit: the engine carries a
        running cost basis per account (seeded from `Account.cost_basis`) and reduces it
        pro rata on a sale, which is exactly the moving-average method a realization tax
        like Austria's KESt requires. A regime that taxes the gross — a lijfrente
        uitkering is taxed in full, basis or no basis — ignores it.

        `owner_person_id` is who holds the account, or `None` for a joint one. A domain
        fact rather than a tax fact, which is why it sits on the country-neutral
        protocol: a citizenship overlay charges per person, and the engine is the only
        thing that knows the owner. Both residence regimes ignore it, but the engine
        keys its within-year running totals by it — a loss one person realises must not
        offset a gain their partner realises.

        `year` is the tax year the sale falls in. `cfg` is already resolved for it, so a
        residence regime never needs it; a citizenship overlay does, because it resolves
        its own country's figures for the same year.
        """
        ...

    def annual_basis_step_up(self, s: YearState, cfg: ConfigT) -> dict[str, np.ndarray]:
        """How much the year's annual tax charge adds to cost basis, per treatment, per run.

        Income that was taxed while the holding was still held must not be taxed a
        second time when it is sold, so a regime that charges `annual_investment_tax` on
        deemed-distributed income raises the basis by that income. Austria states this
        outright (§ 186 Abs 3 InvFG). Keyed by treatment because the base can differ by
        treatment (a non-reporting fund is charged on an estimate, not on what it
        reported); the engine spreads each figure across that treatment's accounts in
        proportion to the income each earned.

        Empty for a regime that taxes the holding itself rather than its income — Box 3
        is charged on wealth and creates no acquisition cost.
        """
        ...

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        """The treatments `withdrawal_tax` can charge on.

        Purely an optimisation: it lets the engine skip the call for the common untaxed
        case. It says nothing about where cash may be swept — that is
        `sweep_excluded_treatments`, and conflating the two is what stopped a
        realization-tax regime investing at all.
        """
        ...

    def sweep_excluded_treatments(self) -> frozenset[str]:
        """The treatments surplus cash must never be swept *into*.

        Separate from `withdrawal_taxed_treatments` on purpose, because the two only
        look alike under NL. There the sole withdrawal-taxed wrapper is the lijfrente,
        which is also the last place spare cash should go. Under a realization tax every
        ordinary brokerage account is taxed on the way out and is still precisely where
        surplus cash belongs — collapsing the two sets leaves such a regime unable to
        invest anything.

        This one means "locked, penalised, or otherwise a bad destination", which is a
        statement about the wrapper, not about when tax falls due.
        """
        ...

    def valid_treatments(self) -> frozenset[str]:
        """The tax_treatment keys this regime understands. Used to validate Account rows."""
        ...

    def actual_return_treatments(self) -> frozenset[str]:
        """The tax_treatment keys whose balances form the actual-return base.

        The engine tracks net inflows into accounts with these treatments and derives
        `YearState.investment_gain` from their year-on-year value change. Bank/savings
        treatments are deliberately absent for NL: the engine cannot yet separate a cash
        account's interest from the household's ordinary in/out flows.
        """
        ...


def regime_for(country: str) -> TaxRegime[Any]:
    """The regime implementation for an ISO country code.

    The return is `TaxRegime[Any]` because the country is a runtime string: which config
    class the regime expects is only knowable once `country` is. Callers pair it with
    `resolve_tax_config(country, ...)` for the same country.

    Args:
        country: ISO 3166-1 alpha-2 code, e.g. `"NL"`.

    Returns:
        The `TaxRegime` for that country.

    Raises:
        KeyError: if no regime is implemented for `country`.
    """
    registry = _registry()
    if country not in registry:
        msg = f"no tax regime for country {country!r}"
        raise KeyError(msg)
    return registry[country]


@cache
def _registry() -> dict[str, TaxRegime[Any]]:
    """The one registry both `regime_for` and `registered_countries` read.

    Cached because the regimes are stateless — every method takes the year's state and
    the config as arguments — so one instance each is all there ever needs to be.
    """
    # Imported here, not at module scope: tax.nl.regime imports YearState from this
    # module, so a top-level import would be circular.
    from vuurtoren.tax.at.regime import ATTaxRegime  # noqa: PLC0415  # breaks an import cycle
    from vuurtoren.tax.nl.regime import NLTaxRegime  # noqa: PLC0415  # breaks an import cycle

    return {"NL": NLTaxRegime(), "AT": ATTaxRegime()}


def registered_countries() -> list[str]:
    """ISO codes a household may set as its tax country, sorted.

    NOT `TAX_CONFIG`'s keys. That registry holds *figures*, and the US set is registered
    there as a citizenship overlay's parameters — somewhere a household is taxed from,
    never somewhere it lives. Offering "US" as a residence would 404 the projection.
    """
    return sorted(_registry())
