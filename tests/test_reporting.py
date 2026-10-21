"""The FBAR/FATCA worksheet, and the exchange-rate direction it turns on."""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.domain import Account, AccountKind, FilingStatus, Person
from vuurtoren.reporting.fbar import FBAR_AGGREGATE_USD, worksheet_for
from vuurtoren.reporting.treasury_rates import (
    TreasuryRate,
    TreasuryRateUnavailable,
    parse_rate,
    year_end_rate,
)

# The payload shape recorded in docs/decisions.md from a live call, trimmed to what is read.
FEED = """
{"data": [{"record_date": "2025-12-31", "country_currency_desc": "Euro Zone-Euro",
           "exchange_rate": "0.851", "effective_date": "2025-12-31"}]}
"""
RATE = TreasuryRate(currency="EUR", record_date="2025-12-31", rate=Decimal("0.851"))
MONTHS = [date(2026, m, 1) for m in range(1, 13)] + [date(2027, 1, 1)]


def _person(status: FilingStatus = "single") -> Person:
    return Person(id=1, household_id=1, name="Sam", us_person=True, us_filing_status=status)


def _account(
    account_id: int,
    name: str,
    kind: AccountKind = AccountKind.CASH,
    owner_person_id: int | None = None,
) -> Account:
    return Account(
        id=account_id,
        household_id=1,
        name=name,
        kind=kind,
        tax_treatment="nl.box3_bank",
        manual_value=Decimal(0),
        owner_person_id=owner_person_id,
    )


# --- the rate ---------------------------------------------------------------------


def test_the_rate_is_read_as_foreign_currency_per_dollar() -> None:
    """Treasury's convention, and the reciprocal of how prices.py stores the ECB rate."""
    rate = parse_rate(FEED, currency="EUR")

    assert rate.rate == Decimal("0.851")
    assert rate.record_date == "2025-12-31"


def test_converting_to_dollars_divides_rather_than_multiplies() -> None:
    """The trap this module exists to close.

    €100,000 is about $117,509, not $85,100. Inverting the rate inflates — or here,
    deflates — every reported balance by roughly 38 %, which on a threshold test is the
    difference between a form filed and a form missed.
    """
    usd = RATE.to_usd(Decimal(100_000))

    assert usd > Decimal(100_000), "a euro is worth more than a dollar; dollars must be more"
    assert round(usd, 2) == pytest.approx(Decimal("117508.81"), abs=Decimal("0.01"))


def test_the_rate_is_exact_rather_than_a_float() -> None:
    """Invariant #4: an FX rate never round-trips through a C double."""
    assert isinstance(parse_rate(FEED, currency="EUR").rate, Decimal)
    assert parse_rate(FEED, currency="EUR").rate == Decimal("0.851")


def test_an_empty_feed_and_an_unknown_currency_both_fail_by_name() -> None:
    """Treasury publishes specific dates, so a miss is a fixable mistake, not an outage."""
    with pytest.raises(TreasuryRateUnavailable):
        parse_rate('{"data": []}', currency="EUR")
    with pytest.raises(TreasuryRateUnavailable, match="JPY"):
        year_end_rate(2025, currency="JPY", fetch=lambda _url: FEED)


@pytest.mark.parametrize(
    "text",
    [
        "<html>Service unavailable</html>",
        '{"data": [{"record_date": "2025-12-31"}]}',
        '{"data": [{"record_date": "2025-12-31", "exchange_rate": "n/a"}]}',
        '{"data": [{"record_date": "2025-12-31", "exchange_rate": "0"}]}',
    ],
    ids=["html", "no-rate", "not-a-number", "zero"],
)
def test_a_malformed_feed_is_unavailable_rather_than_a_crash(text: str) -> None:
    """The route answers 502 for TreasuryRateUnavailable; anything else escaped as a 500."""
    with pytest.raises(TreasuryRateUnavailable):
        parse_rate(text, currency="EUR")


def test_the_year_end_date_is_what_gets_requested() -> None:
    """The instructions say the last day of the tax year, so that is the date requested."""
    seen: list[str] = []

    def fetch(url: str) -> str:
        seen.append(url)
        return FEED

    year_end_rate(2025, fetch=fetch)

    assert "2025-12-31" in seen[0]
    assert "Euro%20Zone-Euro" in seen[0]


# --- the worksheet ----------------------------------------------------------------


def _balances(**by_id: list[float]) -> dict[int, np.ndarray]:
    return {int(k[1:]): np.array([v]) for k, v in by_id.items()}


def test_the_peak_is_the_maximum_month_not_the_year_end() -> None:
    """The pairing both forms require: peak during the year, year-end rate.

    The account here ends the year at €1,000 and touched €500,000 in June. Reporting the
    year-end figure would say no form is due; the peak says both are.
    """
    balances = _balances(a1=[10_000.0] * 5 + [500_000.0] + [1_000.0] * 7)

    sheet = worksheet_for(
        _person(),
        [_account(1, "Dutch savings")],
        months=MONTHS,
        balances=balances,
        year=2026,
        rate=RATE,
    )

    assert sheet.accounts[0].peak_local == Decimal(500_000)
    assert sheet.accounts[0].year_end_local == Decimal(1_000)
    assert sheet.fbar_triggered
    assert sheet.fatca_triggered
    assert sheet.fatca_trigger_reason == "any_time"


def test_a_small_household_triggers_neither_form() -> None:
    """The worksheet has to be able to say no, or it says nothing."""
    sheet = worksheet_for(
        _person(),
        [_account(1, "Dutch savings")],
        months=MONTHS,
        balances=_balances(a1=[5_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert not sheet.fbar_triggered
    assert not sheet.fatca_triggered
    assert sheet.fatca_trigger_reason is None


def test_a_mortgage_is_excluded_rather_than_netted_off() -> None:
    """A liability is not a financial account, and must not shrink the aggregate."""
    accounts = [_account(1, "Dutch savings"), _account(2, "Mortgage", kind=AccountKind.DEBT)]

    sheet = worksheet_for(
        _person(),
        accounts,
        months=MONTHS,
        balances=_balances(a1=[60_000.0] * 13, a2=[-300_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert [a.name for a in sheet.accounts] == ["Dutch savings"]
    assert sheet.aggregate_peak_usd > FBAR_AGGREGATE_USD


def test_a_joint_account_counts_whole_and_not_by_filing_share() -> None:
    """Reporting an interest is not taxing a share.

    `USCitizenshipOverlay` halves a jointly held account for a married-filing-separately
    filer. Both forms take the full value, and a worksheet that borrowed the tax rule
    would under-report by half.
    """
    joint = _account(1, "Joint brokerage")  # no owner_person_id == household-level
    assert joint.owner_person_id is None

    sheet = worksheet_for(
        _person("married_filing_separately"),
        [joint],
        months=MONTHS,
        balances=_balances(a1=[400_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert sheet.accounts[0].peak_local == Decimal(400_000)


def test_another_persons_account_is_not_on_this_worksheet() -> None:
    """The forms are per filer, so a non-US spouse's own account is not reported here."""
    theirs = _account(2, "Alex's ISA", owner_person_id=2)

    sheet = worksheet_for(
        _person(),
        [_account(1, "Sam's savings", owner_person_id=1), theirs],
        months=MONTHS,
        balances=_balances(a1=[20_000.0] * 13, a2=[900_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert [a.name for a in sheet.accounts] == ["Sam's savings"]


def test_the_married_filing_jointly_thresholds_are_the_higher_pair() -> None:
    """Getting these backwards would report a form that is not due, every year."""
    single = worksheet_for(
        _person("single"),
        [_account(1, "S")],
        months=MONTHS,
        balances=_balances(a1=[250_000.0] * 13),
        year=2026,
        rate=RATE,
    )
    joint = worksheet_for(
        _person("married_filing_jointly"),
        [_account(1, "S")],
        months=MONTHS,
        balances=_balances(a1=[250_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert single.fatca_triggered
    assert not joint.fatca_triggered


def test_a_joint_return_s_form_8938_counts_the_spouse_s_assets() -> None:
    """Form 8938 for MFJ reads assets "you or your spouse" hold; the FBAR stays per person.

    Each spouse holding 250,000 is 500,000 on the joint return, over its 400,000 last-day
    threshold. Counting only the US person's own 250,000 said the form was not due.
    """
    sheet = worksheet_for(
        _person("married_filing_jointly"),
        [
            _account(1, "Sam's savings", owner_person_id=1),
            _account(2, "Alex's ISA", owner_person_id=2),
        ],
        months=MONTHS,
        balances=_balances(a1=[250_000.0 * 0.851] * 13, a2=[250_000.0 * 0.851] * 13),
        year=2026,
        rate=RATE,
    )

    assert sheet.fatca_triggered
    assert sheet.fatca_trigger_reason == "last_day"
    assert [a.name for a in sheet.accounts] == ["Sam's savings"]
    assert sheet.aggregate_year_end_usd == pytest.approx(Decimal(250_000), abs=1)


def test_a_year_outside_the_horizon_is_refused_rather_than_reported_as_zero() -> None:
    """Silently reporting every threshold as uncrossed is the worst possible answer."""
    with pytest.raises(ValueError, match="records no month in 2099"):
        worksheet_for(
            _person(),
            [_account(1, "S")],
            months=MONTHS,
            balances=_balances(a1=[1.0] * 13),
            year=2099,
            rate=RATE,
        )


def test_a_house_is_not_a_financial_account() -> None:
    """Directly held real property belongs on neither form.

    Including it would cross both thresholds on the family home alone, which is the
    loudest possible false positive for a worksheet whose whole job is to say whether a
    form is due.
    """
    accounts = [_account(1, "Dutch savings"), _account(2, "Home", kind=AccountKind.REAL_ESTATE)]

    sheet = worksheet_for(
        _person(),
        accounts,
        months=MONTHS,
        balances=_balances(a1=[5_000.0] * 13, a2=[600_000.0] * 13),
        year=2026,
        rate=RATE,
    )

    assert [a.name for a in sheet.accounts] == ["Dutch savings"]
    assert not sheet.fbar_triggered
    assert not sheet.fatca_triggered
