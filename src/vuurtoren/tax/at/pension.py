"""Austrian gesetzliche Pension age.

In code rather than in `parameters.yaml` for the same reason the Dutch AOW schedule is:
`TaxRegime.state_pension_date` takes no `cfg`, so a regime cannot read a figure from the
config when resolving a pension date.

The Regelpensionsalter is 65 for men. For women it rises 60 -> 65 in six-month steps keyed
by birth half-year, from the 1964-01-01 cohort to the 1968-07-01 cohort, which reaches 65.
A person whose sex is not recorded gets 65: for a woman born before mid-1968 that is later
than the law allows, which understates readiness rather than overstating it.

Source: APG § 16 Abs. 6 (BVG Altersgrenzen, BGBl. Nr. 832/1992, § 3),
https://www.ris.bka.gv.at/Dokumente/Bundesnormen/NOR40251097/NOR40251097.pdf
and https://www.pv.at/web/pension/pension-fuer-frauen
Verified 2026-11-09.
"""

from bisect import bisect_right
from calendar import monthrange
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vuurtoren.domain import Sex

# Men, and women from the 1968-07-01 cohort: 65 years, expressed in months for symmetry
# with the Dutch schedule.
STANDARD_AGE_MONTHS = 780  # 65y0m

# Women born before 1964-01-01 keep the old age of 60.
_WOMEN_BEFORE_TRANSITION_MONTHS = 720

# (first birth date of the cohort, age in months), from the APG § 16 Abs. 6 table.
_WOMEN_COHORTS = (
    (date(1964, 1, 1), 726),  # 60y6m
    (date(1964, 7, 1), 732),  # 61y
    (date(1965, 1, 1), 738),  # 61y6m
    (date(1965, 7, 1), 744),  # 62y
    (date(1966, 1, 1), 750),  # 62y6m
    (date(1966, 7, 1), 756),  # 63y
    (date(1967, 1, 1), 762),  # 63y6m
    (date(1967, 7, 1), 768),  # 64y
    (date(1968, 1, 1), 774),  # 64y6m
    (date(1968, 7, 1), STANDARD_AGE_MONTHS),
)


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def _women_age_months(birth_date: date) -> int:
    i = bisect_right([start for start, _ in _WOMEN_COHORTS], birth_date)
    return _WOMEN_COHORTS[i - 1][1] if i else _WOMEN_BEFORE_TRANSITION_MONTHS


def pension_date(birth_date: date, sex: Sex | None) -> date:
    """When the Austrian state pension starts for someone born on `birth_date`.

    Deliberately takes no growth assumption, unlike the Dutch `aow_date`. The AOW is
    indexed to life expectancy by law, so extrapolating it past the legislated table is
    modelling the rule rather than inventing one. Austria's 65 is a flat statutory age
    with no scheduled rise, so applying the household's AOW-drift assumption to it would
    manufacture a retirement delay that no Austrian law provides for. If Austria ever
    legislates a rise, it belongs here as a schedule, the way the AOW's is.
    """
    months = _women_age_months(birth_date) if sex == "female" else STANDARD_AGE_MONTHS
    return _add_months(birth_date, months)
