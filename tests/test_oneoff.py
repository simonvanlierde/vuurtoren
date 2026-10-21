"""Transfer tax starter exemption and gift tax one-time exemption."""

from datetime import date
from decimal import Decimal

from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for
from vuurtoren.tax.nl.oneoff import gift_tax_free_amount, transfer_tax

CFG = defaults_for("NL", 2026, expect=NLTaxConfig)
BORN = date(2000, 3, 15)


def test_starter_under_35_under_the_cap_pays_nothing() -> None:
    """A buyer under 35, buying an own-occupied home under the price cap, owes no duty."""
    assert transfer_tax(
        Decimal(360000),
        buyer_age=29,
        own_occupancy=True,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("0.00"), True)


def test_starter_at_exactly_the_cap_still_qualifies() -> None:
    """A purchase price exactly at the starter cap still qualifies for the exemption."""
    assert transfer_tax(
        Decimal(555000),
        buyer_age=29,
        own_occupancy=True,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("0.00"), True)


def test_one_euro_over_the_cap_loses_the_exemption_entirely() -> None:
    """One euro over the starter cap loses the exemption on the whole price, not just the excess."""
    assert transfer_tax(
        Decimal(555001),
        buyer_age=29,
        own_occupancy=True,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("11100.02"), False)


def test_turning_35_loses_the_exemption() -> None:
    """A buyer who has already turned 35 pays the standard own-occupancy rate, not the exemption."""
    assert transfer_tax(
        Decimal(360000),
        buyer_age=35,
        own_occupancy=True,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("7200.00"), False)


def test_thirty_four_still_qualifies() -> None:
    """A buyer aged 34 still qualifies for the under-35 starter exemption."""
    assert transfer_tax(
        Decimal(360000),
        buyer_age=34,
        own_occupancy=True,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("0.00"), True)


def test_the_exemption_can_only_be_used_once() -> None:
    """A buyer who has already used the starter exemption pays the standard rate on a later buy."""
    assert transfer_tax(
        Decimal(360000),
        buyer_age=29,
        own_occupancy=True,
        starter_exemption_used=True,
        cfg=CFG,
    ) == (Decimal("7200.00"), False)


def test_a_non_primary_residence_pays_the_general_rate() -> None:
    """A non-own-occupied purchase pays the general transfer tax rate, never the exemption."""
    assert transfer_tax(
        Decimal(360000),
        buyer_age=29,
        own_occupancy=False,
        starter_exemption_used=False,
        cfg=CFG,
    ) == (Decimal("28800.00"), False)


def test_gift_within_the_onetime_exemption_is_tax_free() -> None:
    """A gift within the one-time exemption amount is entirely tax-free."""
    assert gift_tax_free_amount(
        Decimal(33129),
        recipient_birth_date=BORN,
        gift_date=date(2029, 6, 1),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("33129.00")


def test_gift_above_the_onetime_exemption_is_capped() -> None:
    """A gift above the one-time exemption is only tax-free up to the exemption amount."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2029, 6, 1),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("33129.00")


def test_a_used_exemption_falls_back_to_the_annual_amount() -> None:
    """Once the one-time exemption is used, only the smaller annual exemption applies."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2029, 6, 1),
        onetime_used=True,
        cfg=CFG,
    ) == Decimal("6908.00")


def test_a_recipient_over_40_gets_only_the_annual_amount() -> None:
    """A recipient over 40 is ineligible for the one-time exemption, only the annual amount."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2041, 6, 1),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("6908.00")


def test_a_recipient_under_18_gets_only_the_annual_amount() -> None:
    """A recipient under 18 is ineligible for the one-time exemption, only the annual amount."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2017, 6, 1),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("6908.00")


def test_gift_exemption_on_the_18th_birthday_gets_the_onetime_exemption() -> None:
    """The 18th birthday is the first day of one-time-exemption eligibility."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2018, 3, 15),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("33129.00")


def test_gift_exemption_on_the_40th_birthday_gets_the_onetime_exemption() -> None:
    """The 40th birthday itself still counts, as the Belastingdienst allows."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2040, 3, 15),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("33129.00")


def test_the_day_after_the_40th_birthday_gets_only_the_annual_amount() -> None:
    """Still "40" in whole years, but past the window the Belastingdienst allows."""
    assert gift_tax_free_amount(
        Decimal(50000),
        recipient_birth_date=BORN,
        gift_date=date(2040, 3, 16),
        onetime_used=False,
        cfg=CFG,
    ) == Decimal("6908.00")


def test_a_29_february_birthday_turns_18_on_28_february() -> None:
    """In a year without 29 February, the window opens on 28 February."""
    born = date(2004, 2, 29)  # turns 18 in 2022, not a leap year

    def free_on(day: date) -> Decimal:
        return gift_tax_free_amount(
            Decimal(50000), recipient_birth_date=born, gift_date=day, onetime_used=False, cfg=CFG
        )

    assert free_on(date(2022, 2, 27)) == Decimal("6908.00")
    assert free_on(date(2022, 2, 28)) == Decimal("33129.00")
