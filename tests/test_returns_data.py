"""Integrity of the curated historical-returns dataset."""

from vuurtoren.returns_data import FIRST_YEAR, HISTORICAL_ANNUAL_RETURNS


def test_the_series_is_long_enough() -> None:
    """The block bootstrap needs decades of years to sample without repeating itself."""
    assert len(HISTORICAL_ANNUAL_RETURNS) >= 50


def test_every_year_is_a_plausible_equity_return() -> None:
    """A real annual global-equity total return sits well inside these bounds.

    A figure outside them is a data-entry slip (a percent left as 19.19 instead of 0.1919).
    """
    for year, r in zip(
        range(FIRST_YEAR, FIRST_YEAR + len(HISTORICAL_ANNUAL_RETURNS)),
        HISTORICAL_ANNUAL_RETURNS,
        strict=True,
    ):
        assert -0.60 <= r <= 1.00, f"{year}: {r} is outside the plausible range"


def test_it_is_a_contiguous_calendar_run() -> None:
    """One float per calendar year with no gaps.

    The bootstrap indexes it by offset, so a missing year would silently shift every
    later year.
    """
    assert FIRST_YEAR == 1970
    assert len(HISTORICAL_ANNUAL_RETURNS) == 2024 - FIRST_YEAR + 1


def test_spot_values_match_the_verified_msci_gross_usd_series() -> None:
    """Pins one year from each verification band (see the module docstring).

    1990 is the year where the net figure (-17.02%) once slipped into this gross series.
    """
    by_year = dict(
        zip(
            range(FIRST_YEAR, FIRST_YEAR + len(HISTORICAL_ANNUAL_RETURNS)),
            HISTORICAL_ANNUAL_RETURNS,
            strict=True,
        )
    )
    assert by_year[1990] == -0.1652
    assert by_year[2008] == -0.4033
    assert by_year[2024] == 0.1919
