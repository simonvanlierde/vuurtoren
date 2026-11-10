"""Box 1: annuity mortgage maths, eigenwoningforfait, Wet Hillen, and gross-to-net income tax."""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.mortgage import annuity_payment
from vuurtoren.tax.nl.aow import aow_year_share
from vuurtoren.tax.nl.box1 import (
    box1_tax_array,
    gross_from_net_array,
    gross_to_net,
    net_housing_tax_effect_array,
    pension_withdrawal_tax_array,
)
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


def test_net_housing_tax_effect_is_exact_to_the_cent() -> None:
    """The forfait and the deduction each round to the cent, not to the euro or further."""
    # WOZ 333,333: forfait 333333 * 0.35% = 1166.6655 -> 1166.67.
    # Deduction (10000 - 1166.67) * 37.56% = 3317.798748 -> 3317.80.
    assert housing(10_000, 333_333) == 3317.80


def test_wet_hillen_phases_out_by_the_year() -> None:
    """In 2030 the Hillen relief is 71.867% - 4 x 4.8% = 52.667% of the excess forfait."""
    # No interest: 1166.67 x (1 - 0.52667) x 37.56% = 207.41 owed.
    assert housing(0, 333_333, year=2030) == -207.41


# --- Box 1 income tax ---
# Hand-computed against the Belastingdienst 2026 tables:
# - brackets (box_1 page): 35.75% to 38,883; 37.56% to 78,426; 49.50% above. From AOW
#   age the first bracket is 17.85%, i.e. without the 17.90% AOW premium.
# - algemene heffingskorting (tabel-algemene-heffingskorting-2026): 3,115 - 6.398% x
#   (income - 29,736); from AOW age 1,556 - 3.195% x (income - 29,736). Never below 0.
# - arbeidskorting (tabel-arbeidskorting-2026), on labour income L: 8.324% x L to
#   11,965; 996 + 31.009% x (L - 11,965) to 25,845; 5,300 + 1.950% x (L - 25,845) to
#   45,592; 5,685 - 6.510% x (L - 45,592), zero from 132,920.
# - ouderenkorting (voorlopige aanslag 2026 page): 2,067 - 15% x (income - 46,002).


def payout_tax(amount: float, other: float, share: float = 0.0) -> float:
    """The Box 1 tax on one lijfrente withdrawal stacked on `other` gross income."""
    got = pension_withdrawal_tax_array(
        np.array([amount]), other_income=np.array([other]), aow_share=share, cfg=CFG
    )
    return float(got[0])


def test_gross_to_net_first_bracket_income() -> None:
    """Within the first bracket, with both kortingen partly built up or phased out."""
    # Tax 30,000 x 35.75% = 10,725.00. AHK 3,115 - 6.398% x 264 = 3,098.10928.
    # AK 5,300 + 1.95% x 4,155 = 5,381.0225. Owed 2,245.86822 -> net 27,754.13.
    assert gross_to_net(Decimal(30000), cfg=CFG) == Decimal("27754.13")


def test_gross_to_net_spans_the_second_bracket() -> None:
    """Both kortingen phase out with the income, which is what the maxima got wrong."""
    # Tax 38,883 x 35.75% + 21,117 x 37.56% = 21,832.2177.
    # AHK 3,115 - 6.398% x 30,264 = 1,178.70928. AK 5,685 - 6.51% x 14,408 = 4,747.0392.
    # Owed 15,906.46922 -> net 44,093.53.
    assert gross_to_net(Decimal(60000), cfg=CFG) == Decimal("44093.53")


def test_gross_to_net_reaches_the_top_bracket() -> None:
    """Past 78,426 the algemene heffingskorting is gone and the arbeidskorting is shrinking."""
    # Tax 13,900.6725 + 39,543 x 37.56% + 21,574 x 49.50% = 39,432.1533. AHK 0.
    # AK 5,685 - 6.51% x 54,408 = 2,143.0392. Owed 37,289.1141 -> net 62,710.89.
    assert gross_to_net(Decimal(100000), cfg=CFG) == Decimal("62710.89")


def test_kortingen_never_push_the_tax_below_zero() -> None:
    """The kortingen floor the tax owed at zero rather than becoming a refund."""
    # 5,000 x 35.75% = 1,787.50 < 3,115 + 8.324% x 5,000 of kortingen: no tax, no refund.
    assert gross_to_net(Decimal(5000), cfg=CFG) == Decimal("5000.00")


def test_gross_to_net_rounds_half_up_to_the_cent() -> None:
    """Below the kortingen no tax is due, so net is gross rounded: half a cent goes up."""
    assert gross_to_net(Decimal("1000.125"), cfg=CFG) == Decimal("1000.13")


def test_gross_from_net_inverts_gross_to_net() -> None:
    """Take-home pay is grossed back up through the same schedule, to the cent."""
    nets = [float(gross_to_net(Decimal(g), cfg=CFG)) for g in (0, 5000, 30000, 60000, 100000)]
    got = gross_from_net_array(np.array(nets), aow_share=0.0, cfg=CFG)
    assert got == pytest.approx([0, 5000, 30000, 60000, 100000], abs=0.01)


@pytest.mark.parametrize("share", [0.0, 0.5, 1.0])
def test_gross_from_net_round_trips_at_every_age(share: float) -> None:
    """Across every bracket and korting knot, below, at and in the year of AOW age."""
    gross = np.arange(0.0, 200_000.0, 250.0)
    tax = box1_tax_array(gross, labour_income=gross, aow_share=share, cfg=CFG)
    got = gross_from_net_array(gross - tax, aow_share=share, cfg=CFG)
    assert got == pytest.approx(gross, abs=0.01)


def test_a_withdrawal_on_no_other_income_is_taxed_from_the_first_bracket() -> None:
    """The flat rate charged 37.56% on everything. Below AOW age, alone, it starts at 35.75%."""
    # 20,000 x 35.75% = 7,150.00, minus the full AHK of 3,115 (no labour income, no AK):
    # 4,035.00. The flat 37.56% charged 7,512.00.
    assert payout_tax(20000, 0) == 4035.00


def test_a_withdrawal_stacked_on_a_wage_pays_the_marginal_rate_with_the_afbouw() -> None:
    """On top of a 60,000 wage the withdrawal pays 37.56% plus the 6.398% AHK phase-out."""
    # T(60,000) = 15,906.46922 (see gross_to_net above). T(70,000), AK still on 60,000:
    # 13,900.6725 + 31,117 x 37.56% = 25,588.2177; AHK 3,115 - 6.398% x 40,264 =
    # 538.90928; owed 25,588.2177 - 538.90928 - 4,747.0392 = 20,302.26922.
    # Difference 4,395.80 (43.958%). The flat rate charged 3,756.00.
    assert payout_tax(10000, 60000) == 4395.80


def test_a_withdrawal_after_aow_age_pays_no_aow_premium_and_gets_the_ouderenkorting() -> None:
    """From AOW age the first bracket is 17.85%, and the ouderenkorting phases out at 15%."""
    # T(20,000) = 3,570 - 1,556 - 2,067 < 0 -> 0.
    # T(50,000): 38,883 x 17.85% + 11,117 x 37.56% = 11,116.1607; AHK 1,556 - 3.195% x
    # 20,264 = 908.5652; OK 2,067 - 15% x 3,998 = 1,467.30. Owed 8,740.2955.
    # The flat 37.56% charged 11,268.00.
    assert payout_tax(30000, 20000, share=1.0) == 8740.30


def test_the_aow_year_blends_the_two_schedules_by_month() -> None:
    """Reaching AOW age in July: the first-bracket rate is the table's 26.80%."""
    # From 25,000 to 26,000 no korting moves (AK stays on the 25,000 of labour), so the
    # marginal tax is the first-bracket rate: (35.75% + 17.85%) / 2 = 26.80%, which is
    # the Belastingdienst's July row.
    assert aow_year_share(date(2058, 7, 15), 2058) == 0.5
    assert payout_tax(1000, 25000, share=0.5) == 268.00


def test_aow_year_share_counts_the_month_of_reaching_aow_age() -> None:
    """January counts in full (the table's 17.85%); a later or earlier year is 0 or 1."""
    assert aow_year_share(date(2058, 1, 1), 2058) == 1.0
    assert aow_year_share(date(2058, 12, 31), 2058) == 1 / 12
    assert aow_year_share(date(2058, 1, 1), 2057) == 0.0
    assert aow_year_share(date(2058, 1, 1), 2059) == 1.0
    assert aow_year_share(None, 2058) == 0.0


def test_pension_withdrawal_tax_is_rounded_to_the_cent_and_ignores_deposits() -> None:
    """1,000.01 x 35.75% = 357.503575 -> 357.50 on top of income that already uses the AHK."""
    got = pension_withdrawal_tax_array(
        np.array([1000.01, -50.0]),
        other_income=np.array([20000.0, 20000.0]),
        aow_share=0.0,
        cfg=CFG,
    )
    assert got.tolist() == [357.50, 0.0]
