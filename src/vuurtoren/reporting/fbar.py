"""FBAR (FinCEN 114) and FATCA (Form 8938) threshold worksheet.

**Read-only, and outside the engine on purpose.** Nothing here can move a projection: it
reads a finished one and reports. That is also why it is a worksheet rather than advice —
it computes figures and states which thresholds those figures appear to cross. It does not
file, and it does not tell anyone what to do.

**The pairing that makes this worth automating.** Both forms want each account's *maximum
value during the year*, converted at the *year-end* rate. Peak in one dimension, year-end in
the other. A monthly engine has every month's balance and can take the peak honestly; a
person reading twelve statements largely cannot. `treasury_rates.py` owns the rate, and the
direction trap that comes with it.

**Joint accounts count whole here, and that is not what the tax layer does.** A US person
with a financial interest in an account reports its full value on the FBAR, and a
married-filing-separately filer reports the full value of a jointly held asset on Form 8938.
`USCitizenshipOverlay._JOINT_SHARE` halves a joint account for MFS because *taxing* a share
is a different question from *reporting* an interest. Two rules, deliberately not shared:
folding them together would either under-report a form or over-tax a return.

Five simplifications, each stated with its direction:

- **Every account is treated as a foreign financial account.** Whether an account is foreign
  turns on where it is *held*, and nothing in `Account` records that — `overlay_treatment`
  says what a holding *is* to the United States, not which broker has it, so a US-domiciled
  fund sitting at a Dutch broker is a foreign account while the same fund at a US broker is
  not. This **over**-reports, which is the safe direction for a form whose penalty for
  omission is severe and whose penalty for including a domestic account is nil.
- **A liability is excluded, not netted.** A mortgage is not a financial account and has no
  place on either form; a DEBT account is dropped rather than subtracted from the total.
- **Directly held real estate is excluded.** A house is not a financial account for the
  FBAR, and Form 8938 asks for foreign *financial assets* — directly held real property is
  not one (a share in a foreign entity that holds property would be, and this app has no
  way to record that). Including it would **over**-report, sometimes hugely: an owner-
  occupied home alone crosses both thresholds.
- **For a joint return, every other owner counts as the spouse.** Form 8938 for married
  filing jointly reads the assets "you or your spouse" hold, and `Person` records no
  spouse, so the joint return's test sums every reportable account in the household. A
  child's own account would therefore **over**-report. The FBAR stays per person: a
  non-US spouse files none, and their accounts are not on the US person's.
- **The peak is over recorded month-ends**, so an intra-month spike between two of them is
  invisible. The forms want the true maximum, so this can **under**-state a peak that both
  neighbouring month-ends sat below.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.domain import AccountKind

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from vuurtoren.domain import Account, FilingStatus, Person
    from vuurtoren.reporting.treasury_rates import TreasuryRate

FBAR_AGGREGATE_USD = Decimal(10_000)
"""FinCEN 114 is due when the aggregate exceeded this **at any time** during the year.

Not a year-end test, and unindexed — it has stood at $10,000 since the Bank Secrecy Act.
"""

# Form 8938, for a filer living **abroad**. Two tests and either one triggers. These are
# four times the domestic figures for an unmarried filer, which is exactly the detail a
# from-memory answer gets wrong.
FATCA_ABROAD_USD: dict[FilingStatus, tuple[Decimal, Decimal]] = {
    "single": (Decimal(200_000), Decimal(300_000)),
    "married_filing_separately": (Decimal(200_000), Decimal(300_000)),
    "married_filing_jointly": (Decimal(400_000), Decimal(600_000)),
}
"""`status -> (last day of the tax year, any time during the year)`."""

# Sources, checked 2026-07-28: https://www.fincen.gov/report-foreign-bank-and-financial-accounts
# and https://www.irs.gov/pub/irs-pdf/i8938.pdf. The Form 8938 instructions are not revised
# annually, so their revision date (Rev. November 2021) is the freshness marker rather than
# a tax year. Re-checked in the January pass.


@dataclass(frozen=True)
class AccountFigures:
    """One account's line on the worksheet, in both currencies."""

    account_id: int
    name: str
    peak_local: Decimal
    """Maximum recorded month-end balance during the year, in the reporting currency."""
    year_end_local: Decimal
    peak_usd: Decimal
    year_end_usd: Decimal


@dataclass(frozen=True)
class Worksheet:
    """What one US person would carry onto the two forms for one year."""

    person_id: int
    person_name: str
    filing_status: FilingStatus
    year: int
    rate: TreasuryRate
    accounts: tuple[AccountFigures, ...]
    aggregate_peak_usd: Decimal
    aggregate_year_end_usd: Decimal
    """The FBAR's aggregate: this person's own and household accounts."""
    fatca_peak_usd: Decimal
    fatca_year_end_usd: Decimal
    """Form 8938's aggregate. The FBAR's, plus the spouse's for a joint return."""
    fbar_triggered: bool
    fatca_triggered: bool
    fatca_last_day_threshold: Decimal
    fatca_any_time_threshold: Decimal

    @property
    def fatca_trigger_reason(self) -> str | None:
        """Which of the two tests crossed, since either alone is enough to trigger."""
        last_day = self.fatca_year_end_usd > self.fatca_last_day_threshold
        any_time = self.fatca_peak_usd > self.fatca_any_time_threshold
        if last_day and any_time:
            return "both"
        if last_day:
            return "last_day"
        if any_time:
            return "any_time"
        return None


def _months_of(months: Sequence[date], year: int) -> list[int]:
    """Indices of the recorded month-ends that fall in `year`."""
    return [i for i, m in enumerate(months) if m.year == year]


_NOT_FINANCIAL = (AccountKind.DEBT, AccountKind.REAL_ESTATE)
"""Kinds neither form asks about. See the module docstring."""


def _reportable(account: Account) -> bool:
    """A liability and a house are not financial accounts. See the module docstring."""
    return account.kind not in _NOT_FINANCIAL


def _has_interest(account: Account, person: Person) -> bool:
    """Whether this person has a financial interest to report.

    Owned by them, or household-level — which this app spells as no owner and both forms
    treat as a joint interest reported whole. The tax layer's filing-status share does not
    apply; the module docstring says why.
    """
    return account.owner_person_id in (person.id, None)


def worksheet_for(
    person: Person,
    accounts: Sequence[Account],
    *,
    months: Sequence[date],
    balances: dict[int, np.ndarray],
    year: int,
    rate: TreasuryRate,
    run: int = 0,
) -> Worksheet:
    """Build one person's worksheet from a finished projection.

    `balances` is `Projection.account_balances`; `run` picks the path, defaulting to the
    deterministic one. A Monte Carlo worksheet would be a distribution of thresholds
    crossed, which is a question nobody asks about a filing obligation.

    Raises:
        ValueError: if the projection records no month in `year`, which means the caller
            asked about a year outside the horizon and every figure would silently be zero.
    """
    indices = _months_of(months, year)
    if not indices:
        first, last = months[0].year, months[-1].year
        msg = f"the projection covers {first}-{last} and records no month in {year}"
        raise ValueError(msg)

    status = person.us_filing_status or "single"
    joint_return = status == "married_filing_jointly"
    figures: list[AccountFigures] = []
    spouse_figures: list[AccountFigures] = []
    for account in accounts:
        if account.id is None or not _reportable(account):
            continue
        own = _has_interest(account, person)
        if not own and not joint_return:
            continue
        series = balances[account.id][run]
        window = series[indices]
        # Floored at zero: a transiently overdrawn account has a maximum value of zero
        # for reporting, not a negative one, and a negative would quietly shrink the
        # aggregate that the threshold test reads.
        peak = Decimal(str(round(float(np.maximum(0.0, window).max()), 2)))
        year_end = Decimal(str(round(float(max(0.0, window[-1])), 2)))
        (figures if own else spouse_figures).append(
            AccountFigures(
                account_id=account.id,
                name=account.name,
                peak_local=peak,
                year_end_local=year_end,
                peak_usd=rate.to_usd(peak),
                year_end_usd=rate.to_usd(year_end),
            )
        )

    # Summed per account, so the aggregate peak is the sum of each account's own maximum
    # rather than the maximum of the summed series. That is what both forms ask for — they
    # are filled in account by account — and it is the larger of the two whenever accounts
    # peak in different months, so it is also the safer reading.
    aggregate_peak = sum((f.peak_usd for f in figures), start=Decimal(0))
    aggregate_year_end = sum((f.year_end_usd for f in figures), start=Decimal(0))
    fatca_peak = aggregate_peak + sum((f.peak_usd for f in spouse_figures), start=Decimal(0))
    fatca_year_end = aggregate_year_end + sum(
        (f.year_end_usd for f in spouse_figures), start=Decimal(0)
    )

    last_day_threshold, any_time_threshold = FATCA_ABROAD_USD[status]
    return Worksheet(
        person_id=person.id,
        person_name=person.name,
        filing_status=status,
        year=year,
        rate=rate,
        accounts=tuple(figures),
        aggregate_peak_usd=aggregate_peak,
        aggregate_year_end_usd=aggregate_year_end,
        fatca_peak_usd=fatca_peak,
        fatca_year_end_usd=fatca_year_end,
        fbar_triggered=aggregate_peak > FBAR_AGGREGATE_USD,
        fatca_triggered=(fatca_year_end > last_day_threshold or fatca_peak > any_time_threshold),
        fatca_last_day_threshold=last_day_threshold,
        fatca_any_time_threshold=any_time_threshold,
    )
