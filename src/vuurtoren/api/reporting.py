"""The US FBAR/FATCA filing-threshold worksheet."""

from typing import Any

from fastapi import APIRouter, HTTPException

from vuurtoren.api.deps import SessionDep, plan_errors_as_400, planned
from vuurtoren.api.schemas import FbarRequest
from vuurtoren.engine import project
from vuurtoren.reporting.fbar import FBAR_AGGREGATE_USD, worksheet_for
from vuurtoren.reporting.treasury_rates import (
    TreasuryRate,
    TreasuryRateUnavailable,
    year_end_rate,
)

router = APIRouter()


@router.post("/api/reporting/fbar")
def fbar_worksheet(body: FbarRequest, session: SessionDep) -> dict[str, Any]:
    """FBAR/FATCA threshold worksheet, one entry per US person in the household.

    Empty `worksheets` for a household with no US person — not a 404. "Nobody here files"
    is a real answer to this question and the caller should be able to render it.
    """
    plan, tax_overrides = planned(session, body)
    us_people = [p for p in plan.people if p.us_person]
    if not us_people:
        return {"year": body.year, "worksheets": [], "rate": None}

    with plan_errors_as_400():
        projection = project(plan, n_runs=1, tax_overrides=tax_overrides)

    if body.usd_per_eur_override is not None:
        rate = TreasuryRate(
            currency="EUR", record_date=f"{body.year}-12-31", rate=body.usd_per_eur_override
        )
    else:
        try:
            rate = year_end_rate(body.year)
        except (TreasuryRateUnavailable, OSError) as e:
            # A projected year has no published rate, and that is the normal case rather
            # than a fault. Say which year and how to proceed instead of failing blank.
            raise HTTPException(
                status_code=502,
                detail=(
                    f"no Treasury rate published for {body.year}-12-31 ({e}). "
                    "Pass usd_per_eur_override to run the worksheet on an assumed rate."
                ),
            ) from e

    try:
        sheets = [
            worksheet_for(
                person,
                plan.accounts,
                months=projection.months,
                balances=projection.account_balances,
                year=body.year,
                rate=rate,
            )
            for person in us_people
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "year": body.year,
        "rate": {"record_date": rate.record_date, "exchange_rate": str(rate.rate)},
        "worksheets": [
            {
                "person_id": s.person_id,
                "person_name": s.person_name,
                "filing_status": s.filing_status,
                "accounts": [
                    {
                        "account_id": a.account_id,
                        "name": a.name,
                        "peak_local": str(a.peak_local),
                        "year_end_local": str(a.year_end_local),
                        "peak_usd": str(round(a.peak_usd, 2)),
                        "year_end_usd": str(round(a.year_end_usd, 2)),
                    }
                    for a in s.accounts
                ],
                "aggregate_peak_usd": str(round(s.aggregate_peak_usd, 2)),
                "aggregate_year_end_usd": str(round(s.aggregate_year_end_usd, 2)),
                "fbar_triggered": s.fbar_triggered,
                "fbar_threshold_usd": str(FBAR_AGGREGATE_USD),
                "fatca_aggregate_peak_usd": str(round(s.fatca_peak_usd, 2)),
                "fatca_aggregate_year_end_usd": str(round(s.fatca_year_end_usd, 2)),
                "fatca_triggered": s.fatca_triggered,
                "fatca_trigger_reason": s.fatca_trigger_reason,
                "fatca_last_day_threshold_usd": str(s.fatca_last_day_threshold),
                "fatca_any_time_threshold_usd": str(s.fatca_any_time_threshold),
            }
            for s in sheets
        ],
    }
