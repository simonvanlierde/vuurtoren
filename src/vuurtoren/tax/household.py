"""`HouseholdTax` — one residence regime plus any per-person citizenship overlays.

Implements `TaxRegime` itself, so `engine.py` keeps holding exactly one regime and none
of its call sites change. Invariant #1 holds: this module names no country.

**It owns the ordering rule**, which is the reason it exists rather than the engine doing
the summing. Residence tax is computed first, then each overlay is handed that figure as
its foreign-tax-credit input. Which tax is computed first is international tax doctrine,
not arithmetic, and it has no business in a country-neutral engine.

With no overlays — every household without a US person — each method returns exactly what
the residence regime returns.
"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from vuurtoren.tax.config import resolve_indexed_tax_config

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    from vuurtoren.domain import Person, ScenarioOverrides
    from vuurtoren.tax.config import TaxConfigBase
    from vuurtoren.tax.overlay import CitizenshipOverlay
    from vuurtoren.tax.regime import Limitation, TaxRegime, YearState


@dataclass(frozen=True)
class HouseholdTax:
    """The household's whole tax picture: where it lives, plus who it belongs to.

    `overlays` pairs a person with the overlay that reaches them. Empty is the common
    case and must stay indistinguishable from the bare residence regime.

    Frozen, and the year's overlay state with it: `close_year` returns the successor that
    carries the next year's state, and `annual_investment_tax` asks without advancing
    anything, so it may be called as often as a caller likes.
    """

    residence: TaxRegime[Any]
    overlays: tuple[tuple[Person, CitizenshipOverlay[Any, Any]], ...] = ()
    carries: tuple[Any, ...] = ()
    """Each overlay's carry into the current year, in `overlays` order; empty before the
    first year. Opaque here: only the overlay that returned one reads it."""
    overrides: ScenarioOverrides | None = None
    """Carried so this can resolve an overlay's own config: the protocol's `cfg` argument
    is the *residence* config, and an overlay needs its country's figures for the same
    year. Resolving them here is what keeps the protocol signature unchanged."""
    index_inflation: float | None = None
    """The rate the overlay's config is indexed by from its source year, as the residence
    config is; None leaves it unindexed. Without it a 2050 bracket stayed in 2026 dollars
    while the income it taxed had inflated for 24 years."""

    def _overlay_cfg(self, overlay: CitizenshipOverlay[Any, Any], year: int) -> TaxConfigBase:
        return resolve_indexed_tax_config(
            overlay.citizenship, year, self.overrides, inflation=self.index_inflation
        )

    @property
    def country(self) -> str:
        """The residence country. A citizenship overlay does not change where you live."""
        return self.residence.country

    @property
    def limitations(self) -> tuple[Limitation, ...]:
        """The residence regime's, unchanged.

        NOTE: the overlays' own simplifications are missing from this, and a US person's
        list is eleven long, each erring in a known direction. They belong to
        `CitizenshipOverlay`, which has no `limitations` member yet; writing them in here
        by hand would put a second copy of the US list outside `tax/us/`.
        """
        return self.residence.limitations

    # --- the two methods an overlay contributes to ---

    def annual_investment_tax(self, s: YearState, cfg: TaxConfigBase) -> np.ndarray:
        """Residence tax, plus each overlay's charge on top of it. Advances nothing."""
        return self.close_year(s, cfg)[0]

    def close_year(self, s: YearState, cfg: TaxConfigBase) -> tuple[np.ndarray, HouseholdTax]:
        """The year's investment tax, and this composite carrying the overlays into the next.

        Call it once per tax year with the year being charged and keep the returned
        composite; the tax is the same figure `annual_investment_tax` gives.
        """
        due = self.residence.annual_investment_tax(s, cfg)
        if not self.overlays:
            return due, self

        shares = _base_shares(s)
        total = due
        carries = self.carries or (None,) * len(self.overlays)
        next_carries = []
        for (person, overlay), carry in zip(self.overlays, carries, strict=True):
            person_slice = s.by_person.get(person.id)
            if person_slice is None:
                next_carries.append(carry)
                continue
            overlay_cfg = self._overlay_cfg(overlay, s.year)
            # The credit input is the residence tax attributable to this person. Split
            # pro rata by their share of the taxed base — an approximation, because a
            # progressive or allowance-bearing residence tax is not linear in the base,
            # and the alternative (re-running the residence regime on one person's slice)
            # would misstate a household allowance just as badly in the other direction.
            charge, carry_out = overlay.annual_tax(
                person_slice,
                overlay_cfg,
                residence_tax=due * shares.get(person.id, 0.0),
                carry=carry,
            )
            total = total + charge
            next_carries.append(carry_out)
        return total, replace(self, carries=tuple(next_carries))

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        year: int,
        cfg: TaxConfigBase,
    ) -> np.ndarray:
        """Residence tax on the sale, plus the owner's overlay if one reaches them.

        A jointly held account (`owner_person_id is None`) is charged by no overlay. The
        filing-status share is an annual-tax concept applied to balances; applying it to a
        realization would be a different rule on a different base, so it is left to the
        overlay's annual charge rather than guessed at here.
        """
        due = self.residence.withdrawal_tax(
            amount,
            treatment=treatment,
            realized_gain=realized_gain,
            owner_person_id=owner_person_id,
            year=year,
            cfg=cfg,
        )
        if not self.overlays or owner_person_id is None:
            return due
        for person, overlay in self.overlays:
            if person.id != owner_person_id:
                continue
            due = due + overlay.withdrawal_tax(
                amount,
                treatment=treatment,
                realized_gain=realized_gain,
                cfg=self._overlay_cfg(overlay, year),
            )
        return due

    # --- everything else is a residence concept and delegates untouched ---

    def annual_housing_adjustment(self, s: YearState, cfg: TaxConfigBase) -> np.ndarray:
        """Delegated: where a home sits is a residence question."""
        return self.residence.annual_housing_adjustment(s, cfg)

    def annual_basis_step_up(self, s: YearState, cfg: TaxConfigBase) -> dict[str, np.ndarray]:
        """Delegated. An overlay's own step-up lands with its own charge, in phase 3."""
        return self.residence.annual_basis_step_up(s, cfg)

    def purchase_costs(
        self,
        price: Decimal,
        *,
        buyer_age: int,
        own_occupancy: bool = True,
        starter_exemption_used: bool,
        mortgage_amount: Decimal,
        cfg: TaxConfigBase,
    ) -> tuple[Decimal, bool]:
        """Delegated: transfer taxes follow the property, not the buyer's passport."""
        return self.residence.purchase_costs(
            price,
            buyer_age=buyer_age,
            own_occupancy=own_occupancy,
            starter_exemption_used=starter_exemption_used,
            mortgage_amount=mortgage_amount,
            cfg=cfg,
        )

    def state_pension_date(self, birth_date: date, *, growth: int) -> date:
        """Delegated: a state pension comes from where you live and work."""
        return self.residence.state_pension_date(birth_date, growth=growth)

    def gift_tax_free_amount(
        self,
        amount: Decimal,
        *,
        recipient_birth_date: date,
        gift_date: date,
        onetime_used: bool,
        cfg: TaxConfigBase,
    ) -> Decimal:
        """Delegated."""
        return self.residence.gift_tax_free_amount(
            amount,
            recipient_birth_date=recipient_birth_date,
            gift_date=gift_date,
            onetime_used=onetime_used,
            cfg=cfg,
        )

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        """The residence set, widened by nothing.

        An overlay charging on a sale is reached through an account the residence regime
        already taxes on the way out, or not at all — phase 3 revisits this if a US
        person turns out to owe tax on a sale the Netherlands does not touch.
        """
        return self.residence.withdrawal_taxed_treatments()

    def sweep_excluded_treatments(self) -> frozenset[str]:
        """Delegated: whether a wrapper is a bad destination is a residence fact."""
        return self.residence.sweep_excluded_treatments()

    def valid_treatments(self) -> frozenset[str]:
        """The residence set, unwidened.

        Overlay keys live on `Account.overlay_treatment` and are validated separately,
        which is the point of them being a different field.
        """
        return self.residence.valid_treatments()

    def actual_return_treatments(self) -> frozenset[str]:
        """Delegated: the tegenbewijs base is a Dutch concept, not a citizenship one."""
        return self.residence.actual_return_treatments()


def _base_shares(s: YearState) -> dict[int, np.ndarray | float]:
    """Each person's share of the household's taxed balances, per run.

    A joint holding counts whole for everyone here, matching how `PersonSlice` presents
    it; the overlay applies its own filing-status fraction to the slice itself. This is
    only used to split the residence tax for the credit input, so it needs to be
    proportionate rather than exact.
    """
    totals: dict[int, np.ndarray] = {}
    for person_id, person_slice in s.by_person.items():
        owned = sum(person_slice.owned.balances.values())
        joint = sum(person_slice.joint.balances.values())
        totals[person_id] = np.asarray(owned) + np.asarray(joint)
    grand = sum(totals.values())
    if not isinstance(grand, np.ndarray):
        return {}
    safe = np.where(grand > 0.0, grand, 1.0)
    return {pid: np.where(grand > 0.0, v / safe, 0.0) for pid, v in totals.items()}
