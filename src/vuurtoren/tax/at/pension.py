"""Austrian gesetzliche Pension age.

In code rather than in `parameters.yaml` for the same reason the Dutch AOW schedule is:
`TaxRegime.state_pension_date` takes no `cfg`, so a regime cannot read a figure from the
config when resolving a pension date.

The Regelpensionsalter is 65.

**Women's transition is deliberately not modelled.** Women's Regelpensionsalter is rising
60 -> 65 in six-month steps keyed by birth date, but the schedule reaches 65 at the
1968-07-01 cohort — so it differs from the men's 65 only for women born before that date,
who are 58 or older today, and it closes entirely in 2033. Modelling it cost a
`Person.sex` field that never once survived a database round-trip, which is its own
evidence that nothing depended on it. Applying the flat 65 errs late rather than early,
understating readiness rather than overstating it.

Source: https://www.pv.at/web/pension/pension-fuer-frauen
Verified 2026-07-28.
"""

from calendar import monthrange
from datetime import date

# Men, and women from the 1968-07-01 cohort: 65 years, expressed in months for symmetry
# with the Dutch schedule.
STANDARD_AGE_MONTHS = 780  # 65y0m


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def pension_date(birth_date: date) -> date:
    """When the Austrian state pension starts for someone born on `birth_date`.

    Deliberately takes no growth assumption, unlike the Dutch `aow_date`. The AOW is
    indexed to life expectancy by law, so extrapolating it past the legislated table is
    modelling the rule rather than inventing one. Austria's 65 is a flat statutory age
    with no scheduled rise, so applying the household's AOW-drift assumption to it would
    manufacture a retirement delay that no Austrian law provides for. If Austria ever
    legislates a rise, it belongs here as a schedule, the way the AOW's is.
    """
    return _add_months(birth_date, STANDARD_AGE_MONTHS)
