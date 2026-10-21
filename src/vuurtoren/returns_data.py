"""Curated historical global-equity annual returns for the historical bootstrap.

WHAT THIS MEASURES
    MSCI World Index annual total returns, GROSS (dividends reinvested, no
    withholding), denominated in USD, one figure per calendar year 1970-2024
    (55 contiguous years). Values are decimal fractions: 0.1919 = +19.19%.

    The series is a *USD* investor's realised return. A euro investor's return
    additionally carries the year's EUR/USD move, which this series does not
    model — a deliberate simplification: the dataset stands in for the shape of
    global-equity sequence risk (drawdowns clustering, recoveries compounding),
    which is what the block bootstrap exists to preserve, and the currency
    overlay would add noise without changing that shape. Documented here rather
    than silently assumed.

CURRENCY BASIS — decided, not defaulted
    USD, kept deliberately. A euro investor's realised
    return also carries the year's EUR/USD move, and the difference is material
    in the 1970s-80s (the dollar lost roughly half its DEM value 1970-1979). USD
    stays because (a) the bootstrap exists to preserve the *sequence shape* of
    global-equity risk — drawdowns clustering, recoveries compounding — which is
    the same in either currency; (b) no primary EUR/DEM-basis series exists for
    the full 1970-2024 window (MSCI's EUR series starts with the euro); and
    (c) mixing a verified USD equity series with a synthetic pre-1999 currency
    overlay would replace a documented simplification with an undocumented one.

SOURCE AND VERIFICATION (verified_on: 2026-07-24)
    2001-2024: PRIMARY. Computed from MSCI's own end-of-day index levels
    (December year-ends, MSCI World Standard, gross, USD, index code 990100,
    app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph).
    Every figure matches the level-derived return to all four decimals. The
    public service refuses dates before 2000, which is where primary stops.
    1970-2000: SECONDARY, cross-checked. Matches the factsheet-sourced gross
    annual return table on en.wikipedia.org/wiki/MSCI_World, whose 24
    overlapping years (2001-2024) agree with the primary computation exactly —
    strong evidence it transcribes the same MSCI series.
    This pass corrected 1990 from -0.1702 (the *net* return, which had slipped
    into this gross series) to -0.1652.

    The bootstrap only needs a realistic sequence of good and bad equity years;
    it does not price any instrument off these numbers.

Note:
    In historical mode this series *is* the equity return assumption: the
    per-account `return_assumption` / `volatility_assumption` are ignored for
    EQUITY accounts (see `engine.historical_returns`). Non-equity accounts keep
    their deterministic `return_assumption`.
"""

FIRST_YEAR = 1970

# One entry per calendar year, starting at FIRST_YEAR. Decimal fractions.
HISTORICAL_ANNUAL_RETURNS: tuple[float, ...] = (
    -0.0198,  # 1970
    0.1956,  # 1971
    0.2355,  # 1972
    -0.1451,  # 1973
    -0.2448,  # 1974
    0.3450,  # 1975
    0.1471,  # 1976
    0.0500,  # 1977
    0.1822,  # 1978
    0.1267,  # 1979
    0.2772,  # 1980
    -0.0330,  # 1981
    0.1127,  # 1982
    0.2328,  # 1983
    0.0577,  # 1984
    0.4177,  # 1985
    0.4280,  # 1986
    0.1676,  # 1987
    0.2395,  # 1988
    0.1719,  # 1989
    -0.1652,  # 1990
    0.1897,  # 1991
    -0.0466,  # 1992
    0.2313,  # 1993
    0.0558,  # 1994
    0.2132,  # 1995
    0.1400,  # 1996
    0.1623,  # 1997
    0.2480,  # 1998
    0.2534,  # 1999
    -0.1292,  # 2000
    -0.1652,  # 2001
    -0.1954,  # 2002
    0.3376,  # 2003
    0.1525,  # 2004
    0.1002,  # 2005
    0.2065,  # 2006
    0.0957,  # 2007
    -0.4033,  # 2008
    0.3079,  # 2009
    0.1234,  # 2010
    -0.0502,  # 2011
    0.1654,  # 2012
    0.2737,  # 2013
    0.0550,  # 2014
    -0.0032,  # 2015
    0.0815,  # 2016
    0.2307,  # 2017
    -0.0820,  # 2018
    0.2840,  # 2019
    0.1650,  # 2020
    0.2235,  # 2021
    -0.1773,  # 2022
    0.2442,  # 2023
    0.1919,  # 2024
)

START_YEARS: tuple[int, ...] = tuple(range(FIRST_YEAR, FIRST_YEAR + len(HISTORICAL_ANNUAL_RETURNS)))
"""The calendar year each index of `HISTORICAL_ANNUAL_RETURNS` means.

The sequential backtest's run r *is* start year `START_YEARS[r]`, and that mapping
travels to the UI on the wire rather than being re-derived from `FIRST_YEAR` on the
other side — one place to be wrong instead of two.
"""
