"""Price fetching and manual entry.

A manual "Refresh prices" action, not a scheduler: Yahoo Finance's public chart
endpoint for exchange-listed accounts, the ECB daily reference feed for EURUSD, and a
manual-entry helper for everything else. No fallback provider and no retries — a
failed fetch is reported per account and the last stored PricePoint stands.

Yahoo replaced Stooq on 2026-07-24: Stooq walled its CSV endpoints behind a JavaScript
proof-of-work challenge, which ended it as a data source for a plain HTTP client. The
stored `PriceSource.STOOQ` enum value survives as the "fetched quote" marker — renaming
a stored enum is a migration this swap does not need.

`refresh_prices` and `record_manual_price` are plain functions; `api/pricing.py` wires them to
an endpoint.
"""

import json
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from sqlalchemy import select

from vuurtoren.domain import PriceSource
from vuurtoren.tables import AccountRow, PricePointRow

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_ECB_NS = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
_CENTS = Decimal("0.01")
_EUR = "EUR"  # the reporting currency: an account quoted in it needs no FX rate


class PriceUnavailable(Exception):  # noqa: N818 -- public name; renaming breaks importers
    """A quote or FX rate could not be read — reported per account, never raised through."""


@dataclass(frozen=True)
class Quote:
    """One fetched market price for a symbol on a trading date."""

    symbol: str
    date: date
    price: Decimal  # native currency, per unit


@dataclass(frozen=True)
class EcbRate:
    """One ECB daily reference rate."""

    date: date
    currency: str
    rate: Decimal  # units of `currency` per 1 EUR, as published


@dataclass(frozen=True)
class RefreshOutcome:
    """One account's refresh result, for the API layer to render."""

    account_id: int
    account_name: str
    ok: bool
    value_eur: Decimal | None = None
    error: str | None = None


def parse_yahoo_chart(text: str) -> Quote:
    """Parse a Yahoo Finance v8 chart response — the quote lives in `meta`.

    `regularMarketPrice` arrives as a JSON float; it goes through `str()` into
    `Decimal` so no binary-float artifact ever reaches a stored price.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        msg = f"Yahoo response is not JSON (bot wall or outage page?): {e}"
        raise PriceUnavailable(msg) from e
    # Any other shape is an outage or an API change. Either way it is this account's
    # failure: let it escape and one bad response aborts the whole refresh.
    try:
        chart = payload.get("chart") or {}
        if chart.get("error"):
            error = chart["error"]
            msg = f"Yahoo error: {error.get('description') or error.get('code')}"
            raise PriceUnavailable(msg)
        results = chart.get("result") or []
        meta = results[0].get("meta", {}) if results else {}
        raw_price = meta.get("regularMarketPrice")
        if raw_price is None:
            msg = f"Yahoo chart response carries no market price for {meta.get('symbol')!r}"
            raise PriceUnavailable(msg)
        price = Decimal(str(raw_price))
        timestamp = meta.get("regularMarketTime")
        quote_date = (
            datetime.fromtimestamp(timestamp, tz=UTC).date()
            if timestamp
            else datetime.now(tz=UTC).date()
        )
        symbol = meta.get("symbol", "")
    except (AttributeError, TypeError, IndexError, ValueError, ArithmeticError) as e:
        msg = f"Yahoo response has an unexpected shape: {e!r}"
        raise PriceUnavailable(msg) from e
    if not price.is_finite() or price <= 0:
        msg = f"Yahoo quotes {symbol!r} at {price}, which is not a price"
        raise PriceUnavailable(msg)
    return Quote(symbol=symbol, date=quote_date, price=price)


def parse_ecb_daily_xml(text: str, currency: str = "USD") -> EcbRate:
    """Parse the ECB `eurofxref-daily.xml` feed for one currency's reference rate."""
    try:
        root = ET.fromstring(text)  # noqa: S314 -- fixed trusted ECB URL, not user input
    except ET.ParseError as e:
        msg = f"ECB feed is not XML (outage page?): {e}"
        raise PriceUnavailable(msg) from e
    dated_cube = root.find(".//ecb:Cube[@time]", _ECB_NS)
    if dated_cube is None:
        msg = "ECB feed has no dated Cube element"
        raise PriceUnavailable(msg)
    rate_cube = dated_cube.find(f"ecb:Cube[@currency='{currency}']", _ECB_NS)
    if rate_cube is None:
        msg = f"ECB feed has no rate for {currency}"
        raise PriceUnavailable(msg)
    try:
        on = date.fromisoformat(dated_cube.attrib["time"])
        rate = Decimal(rate_cube.attrib.get("rate", ""))
    except (ValueError, ArithmeticError) as e:
        msg = f"ECB feed has a malformed {currency} entry: {e!r}"
        raise PriceUnavailable(msg) from e
    if not rate.is_finite() or rate <= 0:
        msg = f"ECB feed quotes {currency} at {rate}, which is not a rate"
        raise PriceUnavailable(msg)
    return EcbRate(date=on, currency=currency, rate=rate)


def http_get(url: str) -> str:
    """GET `url` and return the body as text: stdlib urllib, a short timeout.

    Shared with `reporting/treasury_rates.py`. Callers pass fixed https URLs only.
    """
    # Yahoo rejects urllib's default User-Agent; a plain browser-ish UA is enough.
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (vuurtoren)"})  # noqa: S310 -- callers pass fixed https URLs
    with urlopen(request, timeout=10) as response:  # noqa: S310 -- callers pass fixed https URLs
        return response.read().decode("utf-8")


def _default_fetch_quote(symbol: str) -> str:
    # Encoded whole: a symbol is user-entered text, and a "/", "?" or "#" in it would
    # otherwise rewrite the request path or query.
    return http_get(QUOTE_URL.format(symbol=urllib.parse.quote(symbol, safe="")))


def _default_fetch_ecb() -> str:
    return http_get(ECB_URL)


def _quote_symbol(account: AccountRow) -> str:
    """The Yahoo query symbol for a quote-fetched account.

    # NOTE: Account has no dedicated ticker field (adding one is a domain.py/
    # tables.py schema change, out of scope here), so `isin` doubles as the literal
    # Yahoo symbol (e.g. "VT") for quote-fetched accounts rather than a real ISIN.
    # A genuine ISIN->ticker lookup is a service of its own; add it if this ever
    # needs to resolve real ISINs automatically.
    """
    if not account.isin:
        msg = f"account {account.name!r} has a fetched price_source but no symbol set"
        raise PriceUnavailable(msg)
    return account.isin.strip()


def _units(account: AccountRow) -> Decimal:
    """The unit count a per-unit quote is multiplied by — the manual path's rule too."""
    if account.units is None:
        msg = f"account {account.name!r} has no units to price"
        raise PriceUnavailable(msg)
    return account.units


def _to_cents(value: Decimal) -> Decimal:
    """Round to whole eurocents the same way the `Money` column does (db.py)."""
    return (value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 100


def _upsert_price_point(
    session: Session, account_id: int, on_date: date, **fields: object
) -> PricePointRow:
    """Insert or update the PricePoint for (account_id, on_date).

    The UNIQUE constraint makes a same-day re-run update the row rather than duplicate
    it.
    """
    existing = session.execute(
        select(PricePointRow).where(
            PricePointRow.account_id == account_id, PricePointRow.date == on_date
        )
    ).scalar_one_or_none()
    if existing is None:
        row = PricePointRow(account_id=account_id, date=on_date, **fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        row = existing
    session.flush()
    return row


def _eur_per_unit(currency: str, ecb_xml: str | None, ecb_error: str | None) -> Decimal:
    """EUR per one unit of `currency`, from the already-fetched ECB feed.

    A EUR-quoted account needs no rate at all, so a dead ECB feed only fails the
    accounts that actually need converting.
    """
    if currency == _EUR:
        return Decimal(1)
    if ecb_xml is None:
        msg = f"EUR{currency} rate unavailable: {ecb_error}"
        raise PriceUnavailable(msg)
    return Decimal(1) / parse_ecb_daily_xml(ecb_xml, currency).rate


def refresh_prices(
    session: Session,
    household_id: int,
    *,
    fetch_quote: Callable[[str], str] = _default_fetch_quote,
    fetch_ecb: Callable[[], str] = _default_fetch_ecb,
    today: date | None = None,
) -> list[RefreshOutcome]:
    """Refresh every STOOQ-priced account in the household.

    Each account's quote is converted from its own `currency` to EUR at the ECB daily
    reference rate. Never raises for a single account's failure — that account's outcome
    reports it and its last PricePoint stands.
    """
    accounts = (
        session.execute(
            select(AccountRow).where(
                AccountRow.household_id == household_id,
                AccountRow.price_source == PriceSource.STOOQ,
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        return []

    # A price point is stamped with the local calendar date, not a UTC one.
    on_date = today or datetime.now(tz=UTC).astimezone().date()
    # Fetched once for the whole run and re-parsed per currency: the feed carries every
    # rate, and it is a few KB.
    try:
        ecb_xml: str | None = fetch_ecb()
        ecb_error: str | None = None
    except OSError as e:
        ecb_xml, ecb_error = None, str(e)

    outcomes = []
    for account in accounts:
        try:
            symbol = _quote_symbol(account)
            units = _units(account)
            rate = _eur_per_unit(account.currency, ecb_xml, ecb_error)
            quote = parse_yahoo_chart(fetch_quote(symbol))
        except (PriceUnavailable, OSError, ValueError) as e:
            outcomes.append(RefreshOutcome(account.id, account.name, ok=False, error=str(e)))
            continue

        value_eur = _to_cents(units * quote.price * rate)
        _upsert_price_point(
            session,
            account_id=account.id,
            on_date=on_date,
            price_native=quote.price,
            currency=account.currency,
            fx_rate_to_eur=rate,
            value_eur=value_eur,
            source="yahoo",
        )
        outcomes.append(RefreshOutcome(account.id, account.name, ok=True, value_eur=value_eur))

    session.commit()
    return outcomes


def record_manual_price(
    session: Session,
    account: AccountRow,
    on_date: date,
    *,
    price: Decimal | None = None,
    value: Decimal | None = None,
    fetch_ecb: Callable[[], str] | None = None,
) -> PricePointRow:
    """Write a manual PricePoint (source="manual") for an account.

    Pass `price` (native price per unit) for a unit-priced account — a foreign-currency
    price is converted at the ECB daily reference rate here, so the client never does
    FX math. Pass `value` (a direct EUR amount) for a manual_value account
    (cash, debt, property). Exactly one of the two must be given.

    NOTE: a backdated foreign-currency `price` converts at today's ECB daily reference
    rate, not the historical rate for `on_date` — known limitation of the daily-only feed.
    """
    if price is not None and value is None:
        if account.units is None:
            msg = f"account {account.name!r} has no units to price"
            raise ValueError(msg)
        rate = (
            Decimal(1)
            if account.currency == _EUR
            else Decimal(1)
            / parse_ecb_daily_xml((fetch_ecb or _default_fetch_ecb)(), account.currency).rate
        )
        price_native = price
        currency = account.currency
        value_eur = _to_cents(account.units * price * rate)
    elif value is not None and price is None:
        price_native = value
        currency = _EUR
        rate = Decimal(1)
        value_eur = _to_cents(value)
    else:
        msg = "record_manual_price: pass exactly one of `price` or `value`"
        raise ValueError(msg)

    return _upsert_price_point(
        session,
        account_id=account.id,
        on_date=on_date,
        price_native=price_native,
        currency=currency,
        fx_rate_to_eur=rate,
        value_eur=value_eur,
        source="manual",
    )
