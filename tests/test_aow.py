"""AOW state-pension age tests.

Covers the enacted schedule, resolution to a fixed point, and the assumed
post-schedule growth rate.
"""

from datetime import date

import pytest

from vuurtoren.tax.nl.aow import aow_age_months, aow_date


def test_someone_reaching_it_in_2026_gets_67() -> None:
    """Someone born in 1959 reaches AOW age at exactly 67 years, 0 months."""
    assert aow_age_months(date(1959, 1, 1)) == 804


def test_someone_reaching_it_in_2028_gets_67_years_3_months() -> None:
    """Someone born in 1961 reaches AOW age at 67 years, 3 months, per the enacted schedule."""
    assert aow_age_months(date(1961, 1, 1)) == 807


def test_the_schedule_holds_through_2031() -> None:
    """The enacted schedule keeps AOW age at 67y3m for everyone reaching it through 2031."""
    assert aow_age_months(date(1963, 6, 1)) == 807


def test_beyond_the_schedule_it_grows_at_the_assumed_rate() -> None:
    """Past the enacted schedule, AOW age grows by the assumed rate per decade."""
    # born 1990 -> reaches 67y3m in 2057, two whole decades past 2031 -> +6 months, and
    # 67y9m still lands in 2057, so it settles there
    assert aow_age_months(date(1990, 1, 1)) == 813


def test_zero_growth_freezes_the_schedule() -> None:
    """A zero growth-per-decade assumption freezes AOW age at the last enacted value."""
    assert aow_age_months(date(1990, 1, 1), growth_months_per_decade=0) == 807


def test_faster_growth_pushes_the_age_up() -> None:
    """A higher growth-per-decade assumption raises the projected AOW age above the default."""
    assert aow_age_months(date(1990, 1, 1), growth_months_per_decade=6) > 813


def test_aow_date_is_the_birthday_plus_the_age() -> None:
    """The AOW date is the birthday advanced by the resolved AOW age."""
    d = aow_date(date(1990, 3, 15), growth_months_per_decade=0)
    assert d == date(2057, 6, 15)


def test_resolution_is_stable() -> None:
    """The answer must not depend on how many times you ask."""
    b = date(1990, 1, 1)
    assert aow_age_months(b) == aow_age_months(b)


def test_negative_growth_months_per_decade_raises() -> None:
    """A negative growth-per-decade assumption is rejected as invalid."""
    with pytest.raises(ValueError, match="growth_months_per_decade must be non-negative"):
        aow_age_months(date(1990, 1, 1), growth_months_per_decade=-3)


def test_aow_date_clamps_day_to_month_length() -> None:
    """When the birthday's day doesn't exist in the target month, the AOW date clamps to it."""
    # Born on the 31st, AOW in a 30-day month (April) -> clamped to 30th
    d = aow_date(date(1990, 1, 31), growth_months_per_decade=0)
    assert d == date(2057, 4, 30)
