"""NLTaxRegime — the only implementation of TaxRegime.

A thin adapter. Every calculation lives in the sibling modules; this file maps
tax_treatment keys onto them and holds no arithmetic of its own.
"""

from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.tax.nl.aow import aow_date
from vuurtoren.tax.nl.box1 import net_housing_tax_effect_array, pension_withdrawal_tax_array
from vuurtoren.tax.nl.box3 import box3_tax_array
from vuurtoren.tax.nl.oneoff import gift_tax_free_amount, transfer_tax
from vuurtoren.tax.overlay import TreatmentMaps
from vuurtoren.tax.regime import Limitation

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    from vuurtoren.tax.nl.config import NLTaxConfig
    from vuurtoren.tax.regime import YearState

_LIMITATIONS = (
    Limitation(
        direction="understates",
        nl=(
            "De heffingskortingen staan op hun maximum: de inkomensafhankelijke afbouw "
            "van de algemene heffingskorting en de arbeidskorting is niet gemodelleerd. "
            "Boven de afbouwgrenzen is je nettoloon hier dus te hoog."
        ),
        en=(
            "The heffingskortingen are applied at their maxima — the income-dependent "
            "phase-out of the algemene heffingskorting and arbeidskorting is not "
            "modelled. Past the afbouw points, net wage income here is too high."
        ),
    ),
    Limitation(
        direction="understates",
        nl=(
            "Een lijfrente-uitkering wordt belast tegen één vlak marginaal tarief, niet "
            "tegen de schijven. De lagere premie onder de AOW-leeftijd en de progressie "
            "over een grote eenmalige opname ontbreken beide."
        ),
        en=(
            "A lijfrente withdrawal is taxed at one flat marginal rate rather than "
            "through the brackets. Neither the lower below-AOW premium rate nor bracket "
            "progression on a large one-off withdrawal is modelled."
        ),
    ),
    Limitation(
        direction="either",
        nl=(
            "Box 3 kent de werkelijke rente op banktegoeden niet: die is niet te "
            "scheiden van de gewone geldstromen, dus tegenbewijs en de Wet werkelijk "
            "rendement rekenen alleen met beleggingsrendement."
        ),
        en=(
            "Box 3 does not see the actual interest on bank balances — it cannot be told "
            "apart from ordinary cash flows — so the tegenbewijs and the Wet werkelijk "
            "rendement work from investment returns only."
        ),
    ),
    Limitation(
        direction="understates",
        nl=(
            "Schenkbelasting is niet gemodelleerd. Een schenking boven de vrijstelling "
            "wordt daarom geweigerd in plaats van belast, en erfbelasting aan de "
            "ontvangende kant ontbreekt helemaal."
        ),
        en=(
            "Schenkbelasting is not modelled. A gift above its exemption is refused "
            "rather than taxed, and erfbelasting on the receiving side is absent "
            "entirely."
        ),
    ),
    Limitation(
        direction="overstates",
        nl=(
            "Onder de Wet werkelijk rendement telt een verliesjaar als nul: het verlies "
            "wordt niet meegenomen naar latere jaren. Na een slecht beursjaar is de "
            "belasting hier dus te hoog."
        ),
        en=(
            "Under the Wet werkelijk rendement a loss year counts as zero: the loss is "
            "not carried forward to later years. After a bad market year, tax here is "
            "too high."
        ),
    ),
    Limitation(
        direction="either",
        nl=(
            "Alleen de belastingcijfers voor 2026 zijn met bron vastgelegd. Latere jaren "
            "gebruiken de cijfers van 2026, met vrijstellingen en grenzen geïndexeerd "
            "voor inflatie als die optie aan staat; tarieven blijven gelijk."
        ),
        en=(
            "Only the 2026 tax figures are sourced. Later years reuse the 2026 figures, "
            "with allowances and thresholds indexed for inflation when that option is "
            "on; rates stay the same."
        ),
    ),
)
"""What this regime does not model. See `NLTaxRegime.limitations`.

The same simplifications the sibling modules document in prose — `box1.py` on the
kortingen, `config.py` on the lijfrente rate, `engine.py` on gifts, `box3.py` on the
missing loss carry-forward — said once for a
reader of the *result*. Adding a simplification to a module means adding a line here.
"""

BANK = "nl.box3_bank"
INVESTMENT = "nl.box3_investment"
DEBT = "nl.box3_debt"
HOME = "nl.box1_home"
PENSION = "nl.box1_pension"
NONE = "nl.none"

_TREATMENTS = frozenset({BANK, INVESTMENT, DEBT, HOME, PENSION, NONE})
# BANK is deliberately absent: its actual interest cannot be told apart from ordinary
# cash flows yet, so tegenbewijs/WWR see investment gains only.
_ACTUAL_RETURN_TREATMENTS = frozenset({INVESTMENT})
# Taking money out of a Box 3 investment is not a taxable event; a lijfrente uitkering
# is Box 1 income. Only PENSION is charged on withdrawal.
_WITHDRAWAL_TAXED = frozenset({PENSION})
# The same set, for a different reason: the lijfrente is locked until pension age, so
# surplus cash must never be swept into it. Under NL the two sets coincide; they are
# separate because under a realization tax they do not (see TaxRegime).
_SWEEP_EXCLUDED = frozenset({PENSION})


class NLTaxRegime:
    """The Dutch `TaxRegime`. See `vuurtoren.tax.regime.TaxRegime` for the contract."""

    country = "NL"

    @property
    def limitations(self) -> tuple[Limitation, ...]:
        """See `_LIMITATIONS`."""
        return _LIMITATIONS

    def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
        """Box 3. HOME and PENSION are Box 1 and stay out of the wealth base.

        Fiscal partners are taxed together on the household's wealth with a double
        allowance. People who are not partners are taxed one by one on what they own
        plus an equal share of what is held jointly (the model records no ownership
        fractions), each with their own allowance and debt threshold.
        """
        people = [owner for owner in s.by_owner if owner is not None]
        if s.fiscal_partners or len(people) < 2:
            return self._box3(s.balances_by_treatment, s.investment_gain, s, cfg)
        joint = s.by_owner.get(None, TreatmentMaps())
        share = 1.0 / len(people)
        zero = np.zeros_like(s.home_value)
        total = zero
        for person in people:
            owned = s.by_owner[person]
            balances = {
                k: owned.balances.get(k, zero) + share * joint.balances.get(k, zero)
                for k in {*owned.balances, *joint.balances}
                if k is not None
            }
            # Their own value growth on the actual-return treatments, so the tegenbewijs
            # and the WWR see each person's own return. None stays None: no figure.
            gain = None
            if s.investment_gain is not None:
                gain = sum(
                    (
                        owned.value_growth.get(k, zero) + share * joint.value_growth.get(k, zero)
                        for k in _ACTUAL_RETURN_TREATMENTS
                    ),
                    start=zero,
                )
            total = total + self._box3(balances, gain, s, cfg)
        return total

    def _box3(
        self,
        b: dict[str, np.ndarray],
        actual_return: np.ndarray | None,
        s: YearState,
        cfg: NLTaxConfig,
    ) -> np.ndarray:
        """Box 3 for one taxpayer (or a partner pair) holding the balances in `b`."""
        zero = np.zeros_like(s.home_value)
        bank = b.get(BANK, zero)
        # An overdrawn bank account is money owed, so it belongs in the debt figure. The
        # engine lets cash go negative (it never liquidates investments to cover a
        # shortfall), and clamping the negative to zero here would tax the investments
        # while the borrowing that sustained them stayed invisible.
        overdraft = np.maximum(0.0, -bank)
        # HOME and PENSION are Box 1 — deliberately absent from the wealth base.
        return box3_tax_array(
            bank=np.maximum(0.0, bank),
            investments=np.maximum(0.0, b.get(INVESTMENT, zero)),
            # DEBT balances are stored negative (amount owed, signed); negate to the
            # positive figure box3_tax_array expects. Do NOT clip: a wrong-sign
            # (positive) stored balance yields a negative here and box3_tax_array
            # raises, rather than silently zeroing the deduction.
            debt=-b.get(DEBT, zero) + overdraft,
            # investment_gain is ndarray | None: None means "no actual-return figure
            # available" (no tegenbewijs election possible — falls back to forfaitair),
            # while a run at 0.0 means a proven flat year (a real, electable actual
            # return). Do not conflate the two by defaulting one to the other.
            actual_return=actual_return,
            year=s.year,
            fiscal_partners=s.fiscal_partners,
            cfg=cfg,
        )

    def annual_housing_adjustment(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
        """Hypotheekrenteaftrek netted against the eigenwoningforfait (Box 1)."""
        return net_housing_tax_effect_array(
            s.mortgage_interest_paid, s.home_value, year=s.year, cfg=cfg
        )

    def purchase_costs(
        self,
        price: Decimal,
        *,
        buyer_age: int,
        own_occupancy: bool = True,
        starter_exemption_used: bool,
        mortgage_amount: Decimal,
        cfg: NLTaxConfig,
    ) -> tuple[Decimal, bool]:
        """Overdrachtsbelasting, with the startersvrijstelling where the buyer qualifies.

        `mortgage_amount` is ignored: registering a Dutch mortgage costs notary fees,
        which are a purchase cost but not a tax, and nothing scales with the debt.
        """
        del mortgage_amount
        return transfer_tax(
            price,
            buyer_age=buyer_age,
            own_occupancy=own_occupancy,
            starter_exemption_used=starter_exemption_used,
            cfg=cfg,
        )

    def state_pension_date(self, birth_date: date, *, growth: int) -> date:
        """The AOW date, extrapolating past the legislated schedule by `growth`."""
        return aow_date(birth_date, growth_months_per_decade=growth)

    def gift_tax_free_amount(
        self,
        amount: Decimal,
        *,
        recipient_birth_date: date,
        gift_date: date,
        onetime_used: bool,
        cfg: NLTaxConfig,
    ) -> Decimal:
        """The schenkvrijstelling covering a parental gift — one-time or annual, not both."""
        return gift_tax_free_amount(
            amount,
            recipient_birth_date=recipient_birth_date,
            gift_date=gift_date,
            onetime_used=onetime_used,
            cfg=cfg,
        )

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,  # noqa: ARG002  # country-neutral seam; only an overlay reads it
        year: int,  # noqa: ARG002  # cfg is already resolved for it; only an overlay needs the year
        cfg: NLTaxConfig,
    ) -> np.ndarray:
        """Box 1 tax on a lijfrente uitkering. A Box 3 withdrawal is not a taxable event.

        `realized_gain` is ignored: a uitkering is taxed on the gross amount, because
        the contributions were deducted going in. There is no basis to net off.
        """
        del realized_gain
        if treatment != PENSION:
            return np.zeros_like(amount)
        return pension_withdrawal_tax_array(amount, cfg)

    def annual_basis_step_up(self, s: YearState, cfg: NLTaxConfig) -> dict[str, np.ndarray]:
        """None: Box 3 is charged on the wealth itself, so it creates no acquisition cost.

        Nothing was deemed distributed, so nothing is at risk of being taxed twice.
        """
        del s, cfg
        return {}

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        """Just the pension wrapper — see `_WITHDRAWAL_TAXED`."""
        return _WITHDRAWAL_TAXED

    def sweep_excluded_treatments(self) -> frozenset[str]:
        """Just the pension wrapper: locked until pension age — see `_SWEEP_EXCLUDED`."""
        return _SWEEP_EXCLUDED

    def valid_treatments(self) -> frozenset[str]:
        """The `nl.*` tax_treatment keys an Account may carry under this regime."""
        return _TREATMENTS

    def actual_return_treatments(self) -> frozenset[str]:
        """The treatments whose value change feeds the tegenbewijs/WWR actual return."""
        return _ACTUAL_RETURN_TREATMENTS
