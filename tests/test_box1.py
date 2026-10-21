"""Box 1: annuity mortgage maths, eigenwoningforfait, Wet Hillen, and gross-to-net income tax."""

from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.mortgage import annuity_payment
from vuurtoren.tax.nl.box1 import gross_to_net, net_housing_tax_effect_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for

CFG = defaults_for("NL", 2026, expect=NLTaxConfig)
RATE = float(CFG.hra_max_rate)


def housing(interest: float, woz: float, year: int = 2026) -> float:
    """The engine's net Box 1 housing effect for one run, in euros."""
    return float(
        net_housing_tax_effect_array(np.array([interest]), np.array([woz]), year=year, cfg=CFG)[0]
    )


def test_annuity_payment_matches_the_standard_formula() -> None:
    """The fixed monthly annuity payment matches the standard amortisation formula."""
    # 340000 at 4.2% over 360 months
    got = annuity_payment(Decimal(340000), Decimal("0.042"), 360)
    assert got == Decimal("1662.66")


def test_annuity_payment_with_zero_interest_is_straight_line() -> None:
    """At zero interest, the annuity payment is the principal divided evenly by the term."""
    assert annuity_payment(Decimal(360000), Decimal(0), 360) == Decimal("1000.00")


def test_annuity_payment_rejects_a_zero_term() -> None:
    """A zero-month term is rejected rather than dividing by zero."""
    with pytest.raises(ValueError, match="months must be positive"):
        annuity_payment(Decimal(100000), Decimal("0.04"), 0)


# The forfait alone is read off a mortgage-free year after Wet Hillen has phased out
# (2041), where the whole forfait is taxable: the effect is -(forfait x rate).


def test_eigenwoningforfait_below_the_threshold() -> None:
    """Below the villatax threshold, the eigenwoningforfait is a flat rate of the WOZ value."""
    # 400000 * 0.0035 = 1400.00
    assert housing(0, 400000, year=2041) == round(-1400.00 * RATE, 2)


def test_eigenwoningforfait_above_the_threshold_uses_the_villatax() -> None:
    """Above the threshold, the excess WOZ value is taxed at the higher villatax rate."""
    # Belastingdienst 2026: EUR 4,725 + 2.35% above 1,350,000.
    # 1350000 * 0.0035 + 150000 * 0.0235 = 4725 + 3525 = 8250.00
    assert housing(0, 1500000, year=2041) == round(-8250.00 * RATE, 2)


def test_eigenwoningforfait_at_exactly_the_threshold() -> None:
    """At exactly the villatax threshold, only the low rate applies, with no high-rate tier."""
    forfait = round(float(CFG.ewf_threshold * CFG.ewf_rate), 2)
    assert housing(0, float(CFG.ewf_threshold), year=2041) == round(-forfait * RATE, 2)


def test_net_housing_tax_effect_is_negative_for_a_mortgage_free_owner_in_2026() -> None:
    """Wet Hillen still exempts most of the forfait in 2026, leaving a small negative effect."""
    # ewf on 400000 = 1400.00; Hillen 2026 = 0.71867, so the taxable excess is
    # 1400 * (1 - 0.71867) = 393.862, and the effect is -(393.862 * 0.3756) = -147.93.
    assert housing(0, 400000) == -147.93


def test_net_housing_tax_effect_taxes_the_full_forfait_once_hillen_has_phased_out() -> None:
    """Once Wet Hillen has phased out by 2041, the full eigenwoningforfait is taxable."""
    # By 2041 Hillen has reached zero, so the whole 1400.00 forfait is taxable.
    assert housing(0, 400000, year=2041) == -525.84


def test_net_housing_tax_effect_is_the_plain_deduction_when_interest_exceeds_the_forfait() -> None:
    """Once mortgage interest exceeds the forfait, the net effect is the plain deduction."""
    # interest 14000, ewf on 400000 = 1400 -> (14000 - 1400) * 0.3756
    assert housing(14000, 400000) == 4732.56


def test_net_housing_tax_effect_hillen_never_goes_negative_far_in_the_future() -> None:
    """The phased-out Wet Hillen rate stays at zero rather than going negative far out."""
    assert housing(0, 400000, year=2090) == -525.84


def test_net_housing_tax_effect_array_treats_each_run_on_its_own() -> None:
    """Each run gets its own branch: a deduction, a taxed forfait, and no home at all."""
    got = net_housing_tax_effect_array(
        np.array([14000.0, 0.0, 5000.0]), np.array([400000.0, 400000.0, 0.0]), year=2041, cfg=CFG
    )
    assert got.tolist() == [4732.56, -525.84, 0.0]


# --- gross_to_net ---
# Hand-computed against the 2026 brackets (35.75% to 38,883; 37.56% to 78,426;
# 49.50% above) and the two kortingen at their maxima (3,115 + 5,685 = 8,800).


def test_gross_to_net_first_bracket_income() -> None:
    """Income within the first bracket is taxed at the first-bracket rate, minus kortingen."""
    # 30,000 x 0.3575 = 10,725.00 tax; minus 8,800 kortingen -> 1,925.00 owed.
    assert gross_to_net(Decimal(30000), cfg=CFG) == Decimal("28075.00")


def test_gross_to_net_spans_the_second_bracket() -> None:
    """Income spanning both brackets is taxed at each bracket's own rate, minus kortingen."""
    # 38,883 x 0.3575 + 21,117 x 0.3756 = 21,832.22 tax; minus 8,800 -> 13,032.22.
    assert gross_to_net(Decimal(60000), cfg=CFG) == Decimal("46967.78")


def test_gross_to_net_reaches_the_top_bracket() -> None:
    """Income reaching the top bracket is taxed across all three brackets, minus kortingen."""
    # 13,900.67 + 14,852.35 + 21,574 x 0.4950 = 39,432.15; minus 8,800 -> 30,632.15.
    assert gross_to_net(Decimal(100000), cfg=CFG) == Decimal("69367.85")


def test_kortingen_never_push_the_tax_below_zero() -> None:
    """The kortingen floor the tax owed at zero rather than becoming a refund."""
    # 5,000 x 0.3575 = 1,787.50 < 8,800 of kortingen: tax floors at zero, not a refund.
    assert gross_to_net(Decimal(5000), cfg=CFG) == Decimal("5000.00")


def test_pension_withdrawal_rate_is_derived_from_the_second_bracket() -> None:
    """The pension withdrawal rate is single-sourced from the second Box 1 bracket rate."""
    assert CFG.pension_withdrawal_rate == CFG.box1_rate_2
    assert CFG.hra_max_rate == CFG.box1_rate_2
