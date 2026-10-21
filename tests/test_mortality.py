"""The CBS life table and the survival curves built from it."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from vuurtoren.mortality import (
    MORTALITY_QX,
    TOP_AGE,
    household_survival,
    life_expectancy_at_birth,
)

CBS_E0_2024 = 81.89
"""Period life expectancy at birth CBS publishes beside the table (86042NED, 2024)."""


def test_the_table_reproduces_the_life_expectancy_cbs_publishes() -> None:
    """The transcription check that actually bites.

    Every row feeds this number, so a single mistyped `qx` moves it. The 0.05 tolerance
    covers only the survivors past the table's last row, whose residual life this drops;
    it is far too tight to hide a typo, and tight enough that it caught a wrong life-table
    convention on the first run.
    """
    assert life_expectancy_at_birth() == pytest.approx(CBS_E0_2024, abs=0.05)


def test_the_table_covers_every_age_to_the_open_ended_bucket() -> None:
    """100 rows: ages 0-98 plus CBS's own "99 or older"."""
    assert len(MORTALITY_QX) == 100
    assert TOP_AGE == 99
    assert all(0.0 < q < 1.0 for q in MORTALITY_QX)


def test_mortality_rises_monotonically_through_adult_life() -> None:
    """Past childhood the curve only goes one way; a dip would mean a transposed row."""
    adult = MORTALITY_QX[15:]
    assert all(b >= a for a, b in pairwise(adult))


def test_survival_starts_at_one_and_only_falls() -> None:
    """Being alive today is not in question, and nobody comes back."""
    curve = household_survival([40.0], 600)
    assert curve[0] == pytest.approx(1.0)
    assert np.all(np.diff(curve) <= 0)
    assert np.all(curve >= 0.0)


def test_an_older_household_survives_less_of_the_horizon() -> None:
    """The whole point of reading it against a plan: age moves the curve."""
    young = household_survival([40.0], 480)
    old = household_survival([70.0], 480)
    assert old[-1] < young[-1]


def test_a_couple_outlives_either_of_them_alone() -> None:
    """The joint curve beats either single one: the money outlasts one of two deaths."""
    both = household_survival([65.0, 62.0], 360)
    one = household_survival([65.0], 360)
    other = household_survival([62.0], 360)
    assert both[-1] > one[-1]
    assert both[-1] > other[-1]


def test_an_empty_household_is_treated_as_certain_to_survive() -> None:
    """No people, no mortality claim to make — the overlay must not zero the chart."""
    assert np.all(household_survival([], 120) == 1.0)


def test_a_very_old_household_reuses_the_open_ended_bucket() -> None:
    """Past the table's last row the rate holds rather than indexing off the end."""
    curve = household_survival([120.0], 60)
    assert curve[-1] < curve[0]
    assert np.all(np.isfinite(curve))
