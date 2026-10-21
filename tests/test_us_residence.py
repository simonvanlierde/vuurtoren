"""The NL treaty layer: what Article 25(6) re-sources, and what US tax it leaves standing."""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.domain import FilingStatus, Person
from vuurtoren.engine import Assumptions
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.overlay import PersonSlice, TreatmentMaps, overlays_for
from vuurtoren.tax.us.config import USTaxConfig
from vuurtoren.tax.us.federal import pfic
from vuurtoren.tax.us.overlay import NON_PFIC, USCitizenshipOverlay
from vuurtoren.tax.us.residence import REGISTRY
from vuurtoren.tax.us.residence.nl import USNLTreatyConfig

CFG = defaults_for("US", 2026, expect=USTaxConfig)
TREATY = defaults_for("US-NL", 2026, expect=USNLTreatyConfig)


def _one(x: float) -> np.ndarray:
    return np.array([x])


def _person(status: FilingStatus = "single") -> Person:
    return Person(id=1, household_id=1, name="Sam", us_person=True, us_filing_status=status)


def _slice(*, dividends: float = 0.0, gains: float = 0.0, ucits: float = 0.0) -> PersonSlice:
    return PersonSlice(
        person_id=1,
        owned=TreatmentMaps(
            income={NON_PFIC: _one(dividends), pfic.MTM: _one(ucits)},
            realized_gains={NON_PFIC: _one(gains)},
        ),
        joint=TreatmentMaps(),
        earned_income=_one(0.0),
    )


def _charge(residence: str, s: PersonSlice, *, residence_tax: float) -> float:
    overlay = USCitizenshipOverlay(person=_person(), residence=residence)
    return float(overlay.annual_tax(s, CFG, residence_tax=_one(residence_tax), carry=None)[0][0])


def _niit_on(amount: float) -> float:
    """The uncredited § 1411 charge a single filer bears on `amount` of investment income."""
    excess = max(0.0, amount - float(CFG.niit_threshold_single))
    return min(amount, excess) * float(CFG.niit_rate)


# --- the figures ------------------------------------------------------------------


def test_the_treaty_figures_carry_provenance() -> None:
    """A treaty rate is a tax rate: invariant #3 reaches it too."""
    for name in USNLTreatyConfig.figure_fields():
        assert name in TREATY.provenance, f"{name} ships without provenance"
        assert TREATY.provenance[name].source.startswith("http")
        assert isinstance(TREATY.provenance[name].verified_on, date)


def test_the_registry_answers_for_the_netherlands_and_nowhere_else() -> None:
    """One entry today. A residence with no treaty module gets no relief, not a crash."""
    assert REGISTRY["NL"].residence == "NL"
    assert "AT" not in REGISTRY


# --- the rules --------------------------------------------------------------------


def test_a_portfolio_dividend_is_resourced_but_keeps_its_treaty_rate() -> None:
    """Article 10(2)(b) caps US tax at 15 %; Article 25(6)(b) then preserves exactly that."""
    relief = REGISTRY["NL"].relief(
        us_source_dividends=_one(100_000.0), us_source_gains=_one(0.0), year=2026
    )

    assert relief.resourced == pytest.approx(100_000.0)
    assert relief.preserved_us_tax == pytest.approx(15_000.0)


def test_a_securities_gain_is_resourced_and_leaves_nothing_standing() -> None:
    """Article 14(7): taxable only in the residence state, so there is no US portion to keep."""
    relief = REGISTRY["NL"].relief(
        us_source_dividends=_one(0.0), us_source_gains=_one(80_000.0), year=2026
    )

    assert relief.resourced == pytest.approx(80_000.0)
    assert relief.preserved_us_tax == pytest.approx(0.0)


# --- through the overlay ----------------------------------------------------------


def test_a_retained_us_brokerage_account_is_relieved_to_the_treaty_rate_not_to_zero() -> None:
    """The main case. Dutch tax swamps the US charge, and 15 % of the dividend still stands.

    The interim phase 3 shipped — everything foreign-source — would have credited the whole
    US charge away. Article 25(6)(b) does not allow that, so what is left is the treaty rate
    plus the NIIT, which is charged uncredited for reasons `investment.py` records.
    """
    dividends = 1_000_000.0

    charged = _charge("NL", _slice(dividends=dividends), residence_tax=500_000.0)

    assert charged == pytest.approx(0.15 * dividends + _niit_on(dividends))


def test_the_same_account_gets_no_relief_from_a_residence_with_no_treaty_module() -> None:
    """No entry in the registry means no re-sourcing: US-source income is limited out of § 904.

    Which overstates US tax wherever a treaty exists and this repo has not modelled it —
    the conservative direction, and the reason the default is silence rather than relief.
    """
    s = _slice(dividends=1_000_000.0)

    assert _charge("AT", s, residence_tax=500_000.0) > _charge("NL", s, residence_tax=500_000.0)


def test_a_ucits_holding_is_not_resourced_because_it_is_foreign_source_already() -> None:
    """Nothing to re-source, and no treaty rate to preserve — the credit takes it all."""
    ucits = 200_000.0

    charged = _charge("NL", _slice(ucits=ucits), residence_tax=500_000.0)

    assert charged == pytest.approx(_niit_on(ucits))


# --- currency translation ---------------------------------------------------------


def test_every_money_figure_translates_and_no_rate_does() -> None:
    """`in_currency` is the one boundary where dollars become euros.

    Rates are dimensionless and must not move; `FixedMoney` *must*, which is the trap —
    a figure Congress never indexes is still denominated in dollars. The two skip-lists
    are different lists.
    """
    eur = CFG.in_currency(Decimal("0.851"))

    assert eur.feie_limit == CFG.feie_limit * Decimal("0.851")
    assert eur.niit_threshold_single == CFG.niit_threshold_single * Decimal("0.851")
    assert eur.standard_deduction_mfj == CFG.standard_deduction_mfj * Decimal("0.851")
    assert eur.niit_rate == CFG.niit_rate
    assert eur.ordinary_rate_7 == CFG.ordinary_rate_7


def test_translating_the_thresholds_raises_the_charge_on_a_euro_income() -> None:
    """The direction, which is the whole reason this was worth building.

    A euro buys more than a dollar, so translating a dollar threshold into euros makes it
    a *smaller* number — and more of a euro income sits above it. Leaving the rate at 1,
    which is what the app did before, therefore understated US tax.
    """
    s = _slice(dividends=400_000.0)

    untranslated = _charge("NL", s, residence_tax=0.0)
    translated = float(
        USCitizenshipOverlay(
            person=_person(), residence="NL", usd_to_eur=Decimal("0.851")
        ).annual_tax(s, CFG, residence_tax=_one(0.0), carry=None)[0][0]
    )

    assert translated > untranslated


def test_the_projection_hands_the_household_assumption_to_the_overlay() -> None:
    """A dial nothing reads is a dial that silently does nothing."""
    built = overlays_for([_person()], residence="NL", usd_to_eur=Decimal("0.5"))

    overlay = built[0][1]
    assert isinstance(overlay, USCitizenshipOverlay)  # narrows the protocol to the concrete
    assert overlay.usd_to_eur == Decimal("0.5")


def test_a_nonsense_rate_is_refused_where_it_is_set() -> None:
    """A rate at or below zero is refused where it is set, not where it lands.

    Zero collapses every threshold and a negative one flips its sign; both would surface
    only deep inside a tax ladder, as a charge nobody could explain.
    """
    with pytest.raises(ValueError, match="usd_to_eur"):
        Assumptions(usd_to_eur=Decimal(0))
