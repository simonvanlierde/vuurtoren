"""The citizenship seam, beside the residence seam in `tax/regime.py`.

The United States taxes by citizenship, so a US person resident elsewhere is under two
sets of rules at once and `regime_for(household.tax_country)` cannot express it. This
protocol is the second one, consulted per person rather than per household.

**Deliberately US-shaped, not general machinery.** The United States is the only country
that broadly enforces citizenship-based taxation. For every other expatriate a holding in
another country is not two regimes: the source country withholds at a treaty-reduced rate
and the residence country credits it — one regime plus a leak, which is the call already
recorded for Austria in `docs/decisions.md`.

**Narrower than `TaxRegime`.** `purchase_costs` and `state_pension_date` are residence
concepts, and a protocol that forced an overlay to answer them would be lying about the
asymmetry. What an overlay does have is a `residence_tax` argument on its annual charge,
because a citizenship tax is computed against what the residence country already took.

Composed with a residence regime by `tax/household.py`, which owns the ordering rule.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

# Runtime import, not TYPE_CHECKING: TaxConfigBase is the bound of the protocol's type
# parameter. tax/config.py imports nothing from here, so there is no cycle.
from vuurtoren.tax.config import TaxConfigBase

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

    from vuurtoren.domain import Account, Person


@dataclass(frozen=True)
class TreatmentMaps:
    """`(n_runs,)` arrays keyed by one treatment namespace, never a mix of two.

    Inside a `PersonSlice` the key is the **overlay** treatment — `Account.
    overlay_treatment` — and not the residence treatment, which is the mistake phase 2
    shipped and phase 3 found: invariant #2 forbids an overlay reading an `nl.*` key, so
    keying them that way left an overlay able to sum everything and distinguish nothing,
    which a PFIC charge cannot live with. Inside `YearState.by_owner` the key is the
    residence `tax_treatment`, because there the reader is the residence regime.

    `None` is a legitimate key: an account carrying no overlay classification. It must be
    carried rather than dropped, because a US person's unclassified Dutch savings account
    still earns interest the United States taxes. What `None` *means* is the overlay's
    rule to apply, not the engine's to guess.

    Every map is optional: an overlay reads the ones it cares about and must not trip
    over the rest, exactly as a regime does with `YearState`'s fields.
    """

    balances: dict[str | None, np.ndarray] = field(default_factory=dict)
    income: dict[str | None, np.ndarray] = field(default_factory=dict)
    fund_realized_gains: dict[str | None, np.ndarray] = field(default_factory=dict)
    value_growth: dict[str | None, np.ndarray] = field(default_factory=dict)
    realized_gains: dict[str | None, np.ndarray] = field(default_factory=dict)
    """Gain actually realized by selling, for the year to date.

    Distinct from `fund_realized_gains`, which is a *fund's* internal realizations deemed
    distributed to the holder — an Austrian concept that costs the holder nothing to
    trigger. This one is the holder's own sale.

    Annual rather than per-sale because a realization tax with graduated rates has to
    know the year's other income to place the gain, and only the year-end view has it.
    """


@dataclass(frozen=True)
class PersonSlice:
    """One person's share of the household year, for a citizenship overlay.

    `owned` and `joint` are kept apart on purpose. What fraction of a jointly held
    account falls inside another country's net depends on filing status, which is that
    country's tax rule — and invariant #1 forbids `engine.py` knowing it. So the engine
    states plain ownership facts and the overlay combines them as
    `owned + share * joint` under its own rule.

    Keyed by `Account.overlay_treatment`, the classification that belongs to the
    citizenship layer. The engine copies that field through without interpreting it, so
    invariant #2 holds in both directions: no residence key ever reaches an overlay.
    """

    person_id: int
    owned: TreatmentMaps
    joint: TreatmentMaps
    earned_income: np.ndarray


@runtime_checkable
class CitizenshipOverlay[ConfigT: TaxConfigBase, CarryT](Protocol):
    """A second regime, consulted per person rather than per household.

    Holds no year. What one year leaves for the next (a credit carryforward, a loss pool)
    is a `CarryT` the overlay returns and the caller hands back next year without reading.
    """

    @property
    def citizenship(self) -> str:
        """The country whose citizenship this taxes, which keys its config. Read-only."""
        ...

    def annual_tax(
        self, s: PersonSlice, cfg: ConfigT, *, residence_tax: np.ndarray, carry: CarryT | None
    ) -> tuple[np.ndarray, CarryT]:
        """Tax this citizenship charges for the year, per run, net of any credit.

        `residence_tax` is what the residence regime charged this person for the same
        year — the foreign-tax-credit input. Deciding which tax is computed first is
        doctrine rather than arithmetic, so the caller (`HouseholdTax`) owns the ordering
        and the overlay is simply handed the answer.

        `carry` is what the previous year's call returned, None for the first year. A
        pure function of its arguments: the same inputs give the same charge and the same
        next carry, however often it is asked.

        Returns the charge *on top of* the residence tax, never the combined total, and
        the carry for next year.
        """
        ...

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        cfg: ConfigT,
    ) -> np.ndarray:
        """Tax due on a sale, per run, on top of anything the residence regime charged.

        `treatment` is an *overlay* treatment (`Account.overlay_treatment`), not a
        residence one.
        """
        ...

    def valid_treatments(self) -> frozenset[str]:
        """The `overlay_treatment` keys this overlay understands. Validates Account rows."""
        ...

    def validate_accounts(self, accounts: Sequence[Account], *, person: Person) -> None:
        """Raise if this person may not hold one of these accounts.

        The fail-loud path. A US person holding a PFIC with no mark-to-market election is
        not a tax computation but a hard error, because the honest answer is that they
        should not hold it — modelling the punitive charge would imply the app endorses
        the position.
        """
        ...


def overlays_for(
    people: Sequence[Person], *, residence: str, usd_to_eur: Decimal = Decimal(1)
) -> tuple[tuple[Person, CitizenshipOverlay[Any, Any]], ...]:
    """The citizenship overlays that reach these people, paired with them.

    The counterpart of `regime_for` and the same shape of thing: one registry, no plugin
    discovery. It lives here rather than in `engine.py` because the engine may name no
    country (invariant #1) — it asks for whatever reaches its people and is handed a
    tuple it cannot introspect.

    `residence` is the household's tax country, passed through uninterpreted. A citizenship
    tax is usually mediated by a treaty with the country the person lives in, and only the
    overlay knows whether that matters — the engine hands over the fact and asks nothing.

    `usd_to_eur` is the same shape of hand-over: the engine's arrays are in the household's
    reporting currency and an overlay's figures may not be, so the rate travels with the
    fact rather than the engine deciding whether any translation is needed. Named for the
    only pair that exists today, and honestly so — a second one would rename it rather than
    pretend this had been general all along.

    Empty for every household without a US person, which is what keeps that household's
    numbers bit-for-bit what they were before any of this existed.
    """
    # Imported here, not at module scope: tax.us.overlay imports this module's protocol,
    # so a top-level import would be circular. Same reason as regime_for's.
    from vuurtoren.tax.us.overlay import (  # noqa: PLC0415  # breaks a cycle
        USCitizenshipOverlay,
        check_filing_statuses,
    )

    us_people = [person for person in people if person.us_person]
    check_filing_statuses(us_people)
    return tuple(
        (person, USCitizenshipOverlay(person=person, residence=residence, usd_to_eur=usd_to_eur))
        for person in us_people
    )
