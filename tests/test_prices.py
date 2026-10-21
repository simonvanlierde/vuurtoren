"""Tests for price fetching and manual entry."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Iterator

from vuurtoren import prices
from vuurtoren.db import create_all, make_engine
from vuurtoren.domain import PriceSource
from vuurtoren.prices import (
    EcbRate,
    PriceUnavailable,
    RefreshOutcome,
    parse_ecb_daily_xml,
    parse_yahoo_chart,
    record_manual_price,
    refresh_prices,
)
from vuurtoren.seed import load_household_spec, seed_household
from vuurtoren.tables import AccountRow, HouseholdRow, PricePointRow

EXAMPLE_HOUSEHOLD = Path(__file__).parent.parent / "household.example.toml"

# Trimmed but structurally real Yahoo v8 chart responses (meta carries the quote).
YAHOO_CHART_OK = (
    '{"chart":{"result":[{"meta":{"currency":"USD","symbol":"VT",'
    '"regularMarketPrice":98.90,"regularMarketTime":1784836800}}],"error":null}}'
)
YAHOO_CHART_NO_DATA = (
    '{"chart":{"result":null,"error":{"code":"Not Found",'
    '"description":"No data found, symbol may be delisted"}}}'
)

ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
    xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
  <Cube>
    <Cube time="2026-07-23">
      <Cube currency="USD" rate="1.0921"/>
      <Cube currency="JPY" rate="163.28"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""

ECB_XML_USD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"'
    ' xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">'
    '<Cube><Cube time="2026-07-23"><Cube currency="USD" rate="1.0850"/></Cube></Cube>'
    "</gesmes:Envelope>"
)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    """Provide a Session backed by a temp SQLite file."""
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    with sessionmaker(engine)() as s:
        yield s


@pytest.fixture
def household_id(session: Session) -> int:
    """Seed the example household and return its id."""
    spec = load_household_spec(EXAMPLE_HOUSEHOLD)
    hh_id = seed_household(session, spec)
    # The seed carries no unit counts; a fetched quote is per unit, so give it ten.
    session.query(AccountRow).filter_by(isin="VT").one().units = Decimal(10)
    session.commit()
    return hh_id


# --- pure parsers ---


def test_parse_yahoo_chart_extracts_price_and_date() -> None:
    """A Yahoo chart response parses into its symbol, UTC quote date and market price."""
    quote = parse_yahoo_chart(YAHOO_CHART_OK)
    assert quote.symbol == "VT"
    assert quote.date == date(2026, 7, 23)
    assert quote.price == Decimal("98.90")  # via str(), never a float artifact


def test_parse_yahoo_chart_raises_when_symbol_has_no_data() -> None:
    """A Yahoo error payload raises PriceUnavailable rather than parsing garbage."""
    with pytest.raises(PriceUnavailable, match="delisted"):
        parse_yahoo_chart(YAHOO_CHART_NO_DATA)


def test_parse_yahoo_chart_raises_on_non_json() -> None:
    """An HTML interstitial (bot wall, outage page) raises PriceUnavailable, not JSONDecodeError."""
    with pytest.raises(PriceUnavailable):
        parse_yahoo_chart("<!DOCTYPE html><html>verify your browser</html>")


def test_parse_ecb_daily_xml_extracts_usd_rate() -> None:
    """The ECB daily feed parses into a rate for the requested currency."""
    rate = parse_ecb_daily_xml(ECB_XML)
    assert rate == EcbRate(date=date(2026, 7, 23), currency="USD", rate=Decimal("1.0921"))


def test_parse_ecb_daily_xml_raises_for_a_currency_not_in_the_feed() -> None:
    """A currency absent from the ECB feed raises PriceUnavailable."""
    with pytest.raises(PriceUnavailable):
        parse_ecb_daily_xml(ECB_XML, currency="GBP")


# --- refresh_prices: fake fetchers, no network ---


def test_refresh_prices_converts_usd_to_eur_exactly(session: Session, household_id: int) -> None:
    """A STOOQ quote converts to EUR via the ECB rate, rounded to cents like the Money column."""
    outcomes = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 23),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.ok is True
    # 10 units x 98.90 / 1.0921, rounded to cents the same way the Money column would.
    assert outcome.value_eur == Decimal("905.59")

    stooq_account = session.query(AccountRow).filter_by(isin="VT").one()
    point = session.query(PricePointRow).filter_by(account_id=stooq_account.id).one()
    assert point.price_native == Decimal("98.90")
    assert point.currency == "USD"
    assert point.fx_rate_to_eur == Decimal(1) / Decimal("1.0921")  # survives at full precision
    assert point.value_eur == Decimal("905.59")
    assert point.source == "yahoo"


def test_refresh_prices_is_idempotent_on_a_same_day_rerun(
    session: Session, household_id: int
) -> None:
    """Refreshing twice on the same day does not duplicate the account's price point."""
    for _ in range(2):
        refresh_prices(
            session,
            household_id,
            fetch_quote=lambda _symbol: YAHOO_CHART_OK,
            fetch_ecb=lambda: ECB_XML,
            today=date(2026, 7, 23),
        )

    stooq_account = session.query(AccountRow).filter_by(isin="VT").one()
    points = session.query(PricePointRow).filter_by(account_id=stooq_account.id).all()
    assert len(points) == 1


def test_refresh_prices_updates_the_row_on_a_same_day_rerun_with_a_new_quote(
    session: Session, household_id: int
) -> None:
    """A same-day rerun with a changed quote updates the existing price point in place."""
    refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 23),
    )
    updated_csv = YAHOO_CHART_OK.replace("98.90", "100.00")
    refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: updated_csv,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 23),
    )

    stooq_account = session.query(AccountRow).filter_by(isin="VT").one()
    point = session.query(PricePointRow).filter_by(account_id=stooq_account.id).one()
    assert point.price_native == Decimal("100.00")


def test_refresh_prices_reports_one_account_failure_while_others_succeed(
    session: Session, household_id: int
) -> None:
    """One account's unresolvable symbol is reported as a failure without failing the others."""
    # A second STOOQ account with an unresolvable symbol, alongside the seeded one.
    broken = AccountRow(
        household_id=household_id,
        name="Broken ETF",
        price_source=PriceSource.STOOQ,
        isin="ZZ.NOPE",
    )
    session.add(broken)
    session.commit()

    def fetch_quote(symbol: str) -> str:
        return YAHOO_CHART_NO_DATA if symbol == "ZZ.NOPE" else YAHOO_CHART_OK

    outcomes = refresh_prices(
        session,
        household_id,
        fetch_quote=fetch_quote,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 23),
    )

    by_name = {o.account_name: o for o in outcomes}
    assert by_name["World equity ETF"].ok is True
    assert by_name["Broken ETF"].ok is False
    assert by_name["Broken ETF"].error is not None


def test_refresh_prices_reports_every_account_failing_when_ecb_is_down(
    session: Session, household_id: int
) -> None:
    """An ECB feed failure is reported as a failed outcome for every account, not a raised error."""
    outcomes = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        fetch_ecb=lambda: (_ for _ in ()).throw(OSError("ECB unreachable")),
        today=date(2026, 7, 23),
    )
    assert len(outcomes) == 1
    assert outcomes[0].ok is False
    assert outcomes[0].error is not None


@pytest.mark.parametrize(
    ("ecb", "quote"),
    [
        ("<html><body>Service unavailable<br></body></html>", YAHOO_CHART_OK),
        (ECB_XML, '{"chart":{"result":[{"meta":{"regularMarketPrice":"N/A"}}],"error":null}}'),
        (ECB_XML, '["not", "a", "chart"]'),
    ],
    ids=["ecb-outage-page", "yahoo-na-price", "yahoo-wrong-shape"],
)
def test_a_malformed_response_fails_only_the_account_it_belongs_to(
    session: Session, household_id: int, ecb: str, quote: str
) -> None:
    """An outage page or a placeholder price is that account's failure, not the refresh's.

    The XML parse error and the Decimal error escaped the per-account handler, so one bad
    response aborted the whole refresh with a 500.
    """
    session.add(
        AccountRow(
            household_id=household_id,
            name="Amsterdam ETF",
            price_source=PriceSource.STOOQ,
            isin="IWDA.NL",
            currency="EUR",
            units=Decimal(2),
        )
    )
    session.commit()

    outcomes = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda symbol: YAHOO_CHART_OK if symbol == "IWDA.NL" else quote,
        fetch_ecb=lambda: ecb,
        today=date(2026, 7, 23),
    )

    by_name = {o.account_name: o for o in outcomes}
    assert by_name["Amsterdam ETF"].ok is True
    assert by_name["World equity ETF"].ok is False
    assert by_name["World equity ETF"].error


def test_refresh_prices_leaves_a_eur_quoted_account_unconverted(
    session: Session, household_id: int
) -> None:
    """A EUR-quoted account stores the quote as-is, at rate 1, without needing the ECB feed."""
    eur_account = AccountRow(
        household_id=household_id,
        name="Amsterdam ETF",
        price_source=PriceSource.STOOQ,
        isin="IWDA.NL",
        currency="EUR",
        units=Decimal(2),
    )
    session.add(eur_account)
    session.commit()

    outcomes = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        # The ECB feed being down must not fail an account that needs no conversion.
        fetch_ecb=lambda: (_ for _ in ()).throw(OSError("ECB unreachable")),
        today=date(2026, 7, 23),
    )

    by_name = {o.account_name: o for o in outcomes}
    assert by_name["Amsterdam ETF"].ok is True
    assert by_name["World equity ETF"].ok is False  # USD-quoted, so it does need the rate

    point = session.query(PricePointRow).filter_by(account_id=eur_account.id).one()
    assert point.currency == "EUR"
    assert point.fx_rate_to_eur == Decimal(1)
    assert point.value_eur == Decimal("197.80")


def test_refresh_prices_values_the_holding_not_one_unit(
    session: Session, household_id: int
) -> None:
    """value_eur is units x price x rate, as on the manual path, and no units is a failure."""
    stooq_account = session.query(AccountRow).filter_by(isin="VT").one()
    stooq_account.units = Decimal("2.5")
    session.commit()
    (outcome,) = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 23),
    )
    # 2.5 x 98.90 / 1.0921 = 226.398...
    assert outcome.value_eur == Decimal("226.40")

    stooq_account.units = None
    session.commit()
    (outcome,) = refresh_prices(
        session,
        household_id,
        fetch_quote=lambda _symbol: YAHOO_CHART_OK,
        fetch_ecb=lambda: ECB_XML,
        today=date(2026, 7, 24),
    )
    assert outcome.ok is False
    assert outcome.error is not None
    assert "units" in outcome.error


def test_the_quote_symbol_is_url_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A symbol cannot rewrite the request path or query."""
    seen: list[str] = []
    monkeypatch.setattr(prices, "http_get", lambda url: seen.append(url) or "")
    prices._default_fetch_quote("../v7/x?evil=1#")  # noqa: SLF001  # the URL builder itself
    assert seen == [
        (
            "https://query1.finance.yahoo.com/v8/finance/chart/..%2Fv7%2Fx%3Fevil%3D1%23"
            "?range=1d&interval=1d"
        )
    ]


def test_refresh_prices_returns_no_outcomes_when_no_stooq_accounts_exist(session: Session) -> None:
    """A household with no STOOQ-priced accounts refreshes to an empty outcome list."""
    household = HouseholdRow(name="No stooq accounts")
    session.add(household)
    session.commit()
    outcomes = refresh_prices(
        session, household.id, fetch_quote=lambda _s: "", fetch_ecb=lambda: ""
    )
    assert outcomes == []


# --- manual entry ---


def test_record_manual_price_for_a_unit_priced_account(session: Session, household_id: int) -> None:
    """A unit-priced account's manual price computes value_eur as units times price."""
    account = AccountRow(
        household_id=household_id,
        name="Non-listed index fund",
        price_source=PriceSource.MANUAL,
        units=Decimal("123.456"),
    )
    session.add(account)
    session.commit()

    point = record_manual_price(session, account, date(2026, 7, 23), price=Decimal("81.20"))

    assert point.value_eur == Decimal("10024.63")  # 123.456 * 81.20, rounded to cents
    assert point.source == "manual"
    assert point.currency == "EUR"
    assert point.fx_rate_to_eur == Decimal(1)


def test_manual_price_converts_foreign_currency_at_ecb_rate(
    session: Session, household_id: int
) -> None:
    """The server does the FX — a USD per-unit price lands as EUR."""
    account = AccountRow(
        household_id=household_id,
        name="World ETF",
        price_source=PriceSource.MANUAL,
        units=Decimal(10),
        currency="USD",
    )
    session.add(account)
    session.commit()

    row = record_manual_price(
        session,
        account,
        date(2026, 7, 24),
        price=Decimal("98.90"),
        fetch_ecb=lambda: ECB_XML_USD,
    )
    assert row.currency == "USD"
    assert row.price_native == Decimal("98.90")
    assert row.fx_rate_to_eur == Decimal(1) / Decimal("1.0850")
    # 98.90 * 10 units / 1.0850 = 911.5207... -> 911.52 (cents rounding)
    assert row.value_eur == Decimal("911.52")
    assert row.source == "manual"


@pytest.mark.usefixtures("household_id")
def test_record_manual_price_for_a_manual_value_account(session: Session) -> None:
    """A manual-value account's manual price stores value_eur directly, no conversion."""
    account = session.query(AccountRow).filter_by(isin="NL0000000000").one()
    point = record_manual_price(session, account, date(2026, 7, 23), value=Decimal("52000.00"))
    assert point.value_eur == Decimal("52000.00")
    assert point.source == "manual"


@pytest.mark.usefixtures("household_id")
def test_record_manual_price_requires_exactly_one_of_price_or_value(session: Session) -> None:
    """Passing neither, or both, of price/value is rejected."""
    account = session.query(AccountRow).filter_by(isin="NL0000000000").one()
    with pytest.raises(ValueError, match="exactly one"):
        record_manual_price(session, account, date(2026, 7, 23))
    with pytest.raises(ValueError, match="exactly one"):
        record_manual_price(session, account, date(2026, 7, 23), price=Decimal(1), value=Decimal(1))


@pytest.mark.usefixtures("household_id")
def test_record_manual_price_is_idempotent_on_a_same_day_rerun(session: Session) -> None:
    """Recording twice for the same day updates the one price point rather than adding another."""
    account = session.query(AccountRow).filter_by(isin="NL0000000000").one()
    record_manual_price(session, account, date(2026, 7, 23), value=Decimal("52000.00"))
    record_manual_price(session, account, date(2026, 7, 23), value=Decimal("53000.00"))

    points = session.query(PricePointRow).filter_by(account_id=account.id).all()
    assert len(points) == 1
    assert points[0].value_eur == Decimal("53000.00")


def test_refresh_outcome_is_a_plain_dataclass() -> None:
    """RefreshOutcome defaults error to None for a successful outcome."""
    outcome = RefreshOutcome(account_id=1, account_name="x", ok=True, value_eur=Decimal("1.00"))
    assert outcome.error is None
