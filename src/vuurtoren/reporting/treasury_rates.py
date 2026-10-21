"""The US Treasury Reporting Rates of Exchange — the FBAR/FATCA feed, and only that.

**Beside `prices.py`'s ECB feed, never instead of it.** The Form 8938 instructions are
explicit: "In most cases, you must use the U.S. Treasury Bureau of the Fiscal Service
foreign currency exchange rate for purchasing U.S. dollars", and another publicly available
rate is permitted only where Treasury publishes none — and then the rate and its source must
be disclosed on the form. Reusing the ECB daily reference rate already in this repo would
therefore be a compliance error rather than an approximation. `docs/decisions.md`
(2026-07-28, "FBAR and FATCA figures") records the finding so nobody wires the existing feed
in by reflex.

**The direction is the reciprocal of everything else here, and this is the trap.** Treasury
publishes `exchange_rate` as *foreign currency per one US dollar* — 0.851 euros to the
dollar at 2025-12-31 — while `prices.py` stores `fx_rate_to_eur` as euros per one unit of
foreign currency. So converting a euro balance into dollars **divides** by this rate where
the rest of the codebase multiplies. Inverting it inflates every reported balance by roughly
38 %, which on a threshold test is the difference between a form filed and a form missed.
`to_usd` exists so no caller ever writes the division itself.

**Which rate, and when.** The year-end one: "Use the currency exchange rate on the last day
of the tax year". Paired with each account's *maximum* value during that year — peak in one
dimension, year-end in the other, which is the pairing people get wrong by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from urllib.parse import quote

from vuurtoren.prices import http_get

if TYPE_CHECKING:
    from collections.abc import Callable

RATES_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
    "accounting/od/rates_of_exchange"
    "?filter=country_currency_desc:eq:{currency_desc},record_date:eq:{record_date}"
)
"""No API key, JSON, filterable by currency description and record date."""

CURRENCY_DESC = {"EUR": "Euro Zone-Euro", "USD": "United States-Dollar"}
"""Treasury names a currency by country-and-name, not by ISO code. Only the pairs this app
can hold need an entry; an unmapped currency fails by name rather than fetching nonsense."""


class TreasuryRateUnavailable(RuntimeError):  # noqa: N818 -- reads as prose, and matches prices.PriceUnavailable
    """The feed had no rate for that currency and date.

    Its own exception because the caller's answer is specific: Treasury publishes
    quarter-end dates, so a request for a date it does not carry is a fixable mistake
    rather than an outage.
    """


@dataclass(frozen=True)
class TreasuryRate:
    """One published rate. `rate` is **foreign currency per one US dollar**."""

    currency: str
    record_date: str
    rate: Decimal

    def to_usd(self, amount: Decimal) -> Decimal:
        """`amount`, denominated in `currency`, expressed in US dollars.

        Division, not multiplication — see the module docstring. €100,000 at 0.851 is
        $117,509, not $85,100.
        """
        return amount / self.rate


def parse_rate(text: str, *, currency: str) -> TreasuryRate:
    """Read one rate out of the feed's JSON payload.

    Split from the fetch so the direction can be tested against a recorded payload without
    a network call — which is the thing most worth testing here.
    """
    # Any other shape is an outage page or an API change; the route answers 502 for
    # TreasuryRateUnavailable and would answer 500 for anything else.
    try:
        rows = json.loads(text).get("data") or []
        if not rows:
            msg = f"Treasury feed returned no rate for {currency}"
            raise TreasuryRateUnavailable(msg)
        row = rows[0]
        # Decimal from the raw JSON *text*, never through a float: a rate is exact data
        # (invariant #4), and `json.loads` has already parsed strings as strings here
        # because Treasury publishes exchange_rate as a quoted string.
        record_date = str(row["record_date"])
        rate = Decimal(str(row["exchange_rate"]))
    except (ValueError, AttributeError, TypeError, KeyError, IndexError, ArithmeticError) as e:
        msg = f"Treasury feed has an unexpected shape: {e!r}"
        raise TreasuryRateUnavailable(msg) from e
    if not rate.is_finite() or rate <= 0:
        msg = f"Treasury feed quotes {currency} at {rate}, which is not a rate"
        raise TreasuryRateUnavailable(msg)
    return TreasuryRate(currency=currency, record_date=record_date, rate=rate)


def year_end_rate(
    year: int, *, currency: str = "EUR", fetch: Callable[[str], str] | None = None
) -> TreasuryRate:
    """The 31 December rate for `year` — the one both forms require.

    `fetch` is injectable so tests and the offline path never touch the network, matching
    how `prices.py` takes its fetchers.
    """
    try:
        desc = CURRENCY_DESC[currency]
    except KeyError:
        msg = f"no Treasury currency description for {currency!r}; known: {sorted(CURRENCY_DESC)}"
        raise TreasuryRateUnavailable(msg) from None
    url = RATES_URL.format(currency_desc=quote(desc), record_date=f"{year}-12-31")
    return parse_rate((fetch or http_get)(url), currency=currency)
