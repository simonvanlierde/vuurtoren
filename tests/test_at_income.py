"""Austrian Einkommensteuer: the seven-band tariff, social insurance, and net income."""

from decimal import Decimal

import pytest

from vuurtoren.tax.at.config import ATTaxConfig
from vuurtoren.tax.at.income import (
    gross_to_net,
    income_tax,
    social_insurance,
    sonderzahlung_tax,
)
from vuurtoren.tax.config import defaults_for

CFG = defaults_for("AT", 2026, expect=ATTaxConfig)


def test_the_2026_bands_match_the_published_tariff() -> None:
    """Thresholds and rates as BMF and the AK Steuerwertetabelle publish them for 2026."""
    assert CFG.income_bracket_1_to == Decimal(13539)
    assert CFG.income_rate_1 == Decimal(0)
    assert CFG.income_bracket_2_to == Decimal(21992)
    assert CFG.income_rate_2 == Decimal("0.20")
    assert CFG.income_bracket_6_to == Decimal(1000000)
    assert CFG.income_rate_7 == Decimal("0.55")


def test_income_inside_the_tax_free_band_pays_nothing() -> None:
    """The first band is 0%, so no tax at all below the threshold."""
    assert income_tax(Decimal(13000), cfg=CFG) == Decimal(0)


def test_the_tariff_is_marginal_not_a_cliff() -> None:
    """One euro past a threshold is taxed at the new rate, not the whole income."""
    just_under = income_tax(Decimal(21992), cfg=CFG)
    just_over = income_tax(Decimal(21993), cfg=CFG)
    assert just_over - just_under == pytest.approx(Decimal("0.30"), abs=Decimal("0.001"))


def test_the_published_cumulative_figure_reproduces() -> None:
    """At the top of the second band the AK table gives 1,690.60 of cumulative tax."""
    assert income_tax(Decimal(21992), cfg=CFG) == pytest.approx(
        Decimal("1690.60"), abs=Decimal("0.01")
    )


def test_the_third_band_matches_the_published_cumulative_figure() -> None:
    """At the top of the third band the AK table gives 6,030.40."""
    assert income_tax(Decimal(36458), cfg=CFG) == pytest.approx(
        Decimal("6030.40"), abs=Decimal("0.01")
    )


def test_social_insurance_stops_at_the_ceiling() -> None:
    """Contributions are capped, so a very high salary pays a falling effective rate."""
    at_ceiling = social_insurance(CFG.social_insurance_ceiling, cfg=CFG)
    far_above = social_insurance(CFG.social_insurance_ceiling * 3, cfg=CFG)
    assert at_ceiling == far_above


def test_social_insurance_is_deducted_before_the_tariff() -> None:
    """Contributions reduce the taxable base (§ 16 EStG).

    Applying the tariff to gross instead would overstate Austrian tax by hundreds of
    euros at an ordinary salary, so this is the ordering that matters most here.
    """
    gross = Decimal(60000)
    sv = social_insurance(gross, cfg=CFG)
    # The 12-payment path, so the Jahressechstel split does not obscure the ordering.
    assert gross_to_net(gross, cfg=CFG, sonderzahlungen=False) == gross - sv - max(
        Decimal(0), income_tax(gross - sv, cfg=CFG) - CFG.employee_credit
    )


def test_net_income_rises_monotonically_with_gross() -> None:
    """No salary band leaves someone worse off for earning more."""
    nets = [gross_to_net(Decimal(g), cfg=CFG) for g in (0, 15000, 30000, 60000, 100000, 200000)]
    assert nets == sorted(nets)


def test_a_zero_or_negative_salary_nets_zero() -> None:
    """Guards the boundary rather than returning a negative net."""
    assert gross_to_net(Decimal(0), cfg=CFG) == Decimal(0)
    assert gross_to_net(Decimal(-100), cfg=CFG) == Decimal(0)


# --- Jahressechstel: the 13th and 14th salary ---


def test_the_sonderzahlungen_are_taxed_at_six_percent_not_the_marginal_rate() -> None:
    """A 14-payment salary nets more than the headline tariff implies (§ 67 EStG)."""
    gross = Decimal(60000)
    fourteen = gross_to_net(gross, cfg=CFG)
    twelve = gross_to_net(gross, cfg=CFG, sonderzahlungen=False)
    assert fourteen > twelve
    # Materially so — this was the single biggest approximation before it was modelled.
    assert fourteen - twelve > Decimal(1000)


def test_a_small_jahressechstel_is_exempt_entirely() -> None:
    """Below the Freigrenze nothing is charged, rather than 6% of a small number."""
    assert sonderzahlung_tax(CFG.sonderzahlung_exempt_below, cfg=CFG) == Decimal(0)
    assert sonderzahlung_tax(CFG.sonderzahlung_exempt_below + 1, cfg=CFG) > Decimal(0)


def test_the_freibetrag_is_deducted_before_the_flat_rate() -> None:
    """6% applies to the Jahressechstel less the 620 Freibetrag, not to all of it."""
    sonstige = Decimal(10000)
    expected = (sonstige - CFG.sonderzahlung_allowance) * CFG.sonderzahlung_rate
    assert sonderzahlung_tax(sonstige, cfg=CFG) == pytest.approx(expected)


def test_net_income_still_rises_monotonically_with_sonderzahlungen() -> None:
    """The Freigrenze is a cliff in the tax, but must not make anyone worse off overall."""
    nets = [gross_to_net(Decimal(g), cfg=CFG) for g in (0, 15000, 30000, 60000, 100000, 200000)]
    assert nets == sorted(nets)
