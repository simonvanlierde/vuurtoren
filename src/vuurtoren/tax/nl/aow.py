"""AOW age.

Legislated through 2031; past that it tracks life expectancy and is fixed only five
years ahead, so the projection treats it as an assumption rather than a constant.
"""

from calendar import monthrange
from datetime import date

# Calendar year -> AOW age in months.
# Source: https://www.rijksoverheid.nl/themas/algemene-ouderdomswet-aow/aow-leeftijd
# Verified 2026-07-23.
AOW_SCHEDULE: dict[int, int] = {
    2025: 804,  # 67y0m
    2026: 804,
    2027: 804,
    2028: 807,  # 67y3m
    2029: 807,
    2030: 807,
    2031: 807,
}

_LAST_SCHEDULED_YEAR = max(AOW_SCHEDULE)
_LAST_SCHEDULED_AGE = AOW_SCHEDULE[_LAST_SCHEDULED_YEAR]


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def _scheduled_age(reach_year: int, growth_months_per_decade: int) -> int:
    if reach_year in AOW_SCHEDULE:
        return AOW_SCHEDULE[reach_year]
    if reach_year < min(AOW_SCHEDULE):
        return AOW_SCHEDULE[min(AOW_SCHEDULE)]
    decades = (reach_year - _LAST_SCHEDULED_YEAR) // 10
    return _LAST_SCHEDULED_AGE + decades * growth_months_per_decade


def aow_age_months(birth_date: date, *, growth_months_per_decade: int = 3) -> int:
    """AOW age in months, resolved to a fixed point.

    Your AOW age depends on the year you reach it, which depends on your AOW age. Iterate
    until stable; in practice this settles in one or two rounds.
    """
    if growth_months_per_decade < 0:
        msg = f"growth_months_per_decade must be non-negative, got {growth_months_per_decade}"
        raise ValueError(msg)
    age = _LAST_SCHEDULED_AGE
    for _ in range(8):
        reach_year = _add_months(birth_date, age).year
        nxt = _scheduled_age(reach_year, growth_months_per_decade)
        if nxt == age:
            return age
        age = nxt
    msg = (
        f"AOW age did not converge for birth_date={birth_date} with "
        f"growth_months_per_decade={growth_months_per_decade}"
    )
    raise RuntimeError(msg)


def aow_date(birth_date: date, *, growth_months_per_decade: int = 3) -> date:
    """The date AOW starts: `birth_date` plus the resolved AOW age in months."""
    return _add_months(
        birth_date, aow_age_months(birth_date, growth_months_per_decade=growth_months_per_decade)
    )


def aow_year_share(state_pension_date: date | None, year: int) -> float:
    """The part of `year` a person spends at AOW age, in whole months.

    The month AOW age is reached counts in full: the Belastingdienst charges someone who
    reaches it in January the AOW-age first-bracket rate for the whole year. None (no
    known person) is 0.0, the below-AOW schedule.
    """
    if state_pension_date is None or state_pension_date.year > year:
        return 0.0
    if state_pension_date.year < year:
        return 1.0
    return (13 - state_pension_date.month) / 12
