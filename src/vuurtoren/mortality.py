"""Dutch period life table — the survival half of "rich, broke or dead".

WHAT THIS MEASURES
    `qx`, the probability of dying before reaching the next birthday, for the whole
    Dutch population (both sexes combined), one figure per age 0-99. Index is the age;
    the last entry is the open-ended "99 or older" group CBS publishes as one bucket.

SOURCE AND VERIFICATION (verified_on: 2026-07-28)
    CBS StatLine table 86042NED, "Prognose periode-levensverwachting; geslacht en
    leeftijd", period 2024, Geslacht=T001038 (totaal), field `Sterftekans`. Fetched from
    the CBS OData endpoint rather than transcribed from the web page:
    opendata.cbs.nl/ODataApi/odata/86042NED/TypedDataSet

    `test_mortality.py` re-derives the period life expectancy at birth from this table
    and checks it against the 81.89 years CBS publishes alongside it. That is a genuine
    end-to-end check on the transcription: a single mistyped `qx` moves the answer.

WHY BOTH SEXES COMBINED
    The same call Austria's pension age got (`docs/decisions.md`): `Person` carries no
    sex, and the field would have to survive a database round-trip to be worth anything.
    Dutch female life expectancy runs about three years above male, so a couple's blended
    curve is close to this one and a single person's is out by roughly ±1.5 years of
    expectancy. Stated here rather than silently assumed.

NOT A PREDICTION
    A period table asks "what if today's mortality rates held forever". Actual cohort
    mortality keeps improving, so this understates survival — it makes the chart
    conservative in the direction that matters least, since over-stating death would
    flatter a plan.
"""

from __future__ import annotations

import numpy as np

# One entry per age 0..99; the last is CBS's open-ended "99 or older" bucket.
MORTALITY_QX: tuple[float, ...] = (
    0.00296,
    0.00035,
    0.00018,
    0.00011,
    0.00008,
    0.00007,
    0.00006,
    0.00006,
    0.00005,
    0.00005,
    0.00005,
    0.00005,
    0.00006,
    0.00007,
    0.00009,
    0.00011,
    0.00014,
    0.00017,
    0.00020,
    0.00023,
    0.00025,
    0.00026,
    0.00027,
    0.00028,
    0.00029,
    0.00029,
    0.00031,
    0.00032,
    0.00034,
    0.00036,
    0.00038,
    0.00040,
    0.00042,
    0.00044,
    0.00047,
    0.00050,
    0.00054,
    0.00058,
    0.00062,
    0.00068,
    0.00074,
    0.00081,
    0.00090,
    0.00099,
    0.00108,
    0.00118,
    0.00129,
    0.00141,
    0.00155,
    0.00172,
    0.00191,
    0.00213,
    0.00238,
    0.00265,
    0.00294,
    0.00327,
    0.00363,
    0.00403,
    0.00447,
    0.00495,
    0.00546,
    0.00601,
    0.00660,
    0.00723,
    0.00792,
    0.00865,
    0.00945,
    0.01030,
    0.01128,
    0.01241,
    0.01371,
    0.01518,
    0.01685,
    0.01882,
    0.02105,
    0.02358,
    0.02648,
    0.02975,
    0.03341,
    0.03748,
    0.04224,
    0.04780,
    0.05420,
    0.06187,
    0.07092,
    0.08130,
    0.09338,
    0.10687,
    0.12193,
    0.13873,
    0.15709,
    0.17687,
    0.19860,
    0.22119,
    0.24473,
    0.26957,
    0.29721,
    0.32658,
    0.35700,
    0.40233,
)

TOP_AGE = len(MORTALITY_QX) - 1
"""Ages past the table's end reuse its last `qx` — CBS's own open-ended bucket."""


def life_expectancy_at_birth() -> float:
    """Period life expectancy at age 0, re-derived from `MORTALITY_QX`.

    Exists to be checked against the figure CBS publishes beside the table: it is the
    one number that touches every row, so it catches a transcription slip that eyeballing
    a hundred decimals would not.

    Counts only survivors of each full year (a(x)=1), *not* the textbook a(x)=0.5. That
    is what CBS's own "leeftijd op 31 december" indexing means — a row describes people
    who reach that age at year end — and it is the convention that reproduces their
    published figure: 81.868 here against 81.89, with the remaining 0.02 explained by
    the 1.3% still alive past the table's last row, whose residual life is dropped.
    Using a(x)=0.5 instead reads 82.36, which is how the mismatch was found.
    """
    alive = 1.0
    years = 0.0
    for qx in MORTALITY_QX:
        alive *= 1.0 - qx
        years += alive
    return years


def monthly_survival(start_age_years: float, n_months: int) -> np.ndarray:
    """P(alive at month m), m in 0..n_months-1, for someone `start_age_years` old now.

    Index 0 is 1.0 — being alive today is not in question. Each year's `qx` is spread
    evenly across its twelve months, so the curve steps smoothly rather than in annual
    cliffs; the alternative would put a visible notch on every birthday for no gain in
    accuracy.
    """
    out = np.empty(n_months, dtype=float)
    alive = 1.0
    for m in range(n_months):
        out[m] = alive
        age = int(start_age_years + m / 12.0)
        qx = MORTALITY_QX[min(age, TOP_AGE)]
        alive *= (1.0 - qx) ** (1.0 / 12.0)
    return out


def household_survival(start_ages_years: list[float], n_months: int) -> np.ndarray:
    """P(at least one member of the household is alive) per month.

    "At least one" rather than per-person because that is the question a *plan* asks:
    the money has to last while anybody is still spending it. For a single-person
    household it reduces to that person's own curve. Deaths are treated as independent,
    which overstates joint survival slightly — partners share age, habits and
    circumstance — and there is no Dutch couples table to do better with.
    """
    if not start_ages_years:
        return np.ones(n_months, dtype=float)
    dead_all = np.ones(n_months, dtype=float)
    for age in start_ages_years:
        dead_all *= 1.0 - monthly_survival(age, n_months)
    return 1.0 - dead_all
