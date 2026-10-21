"""Price routes: a manually entered price, and the "Refresh prices" button."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vuurtoren import prices
from vuurtoren.api.deps import SessionDep, get_or_404, household_or_404
from vuurtoren.api.schemas import ManualPriceIn, PricePointOut
from vuurtoren.prices import PriceUnavailable, record_manual_price
from vuurtoren.tables import AccountRow

router = APIRouter()


@router.post("/api/price-points/manual", response_model=PricePointOut, status_code=201)
def create_manual_price(body: ManualPriceIn, session: SessionDep) -> BaseModel:
    """Record a manually-entered per-unit price or direct EUR value for one account."""
    account = get_or_404(session, AccountRow, body.account_id)
    try:
        row = record_manual_price(session, account, body.date, price=body.price, value=body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (PriceUnavailable, OSError) as e:
        raise HTTPException(status_code=502, detail=f"ECB rate unavailable: {e}") from e
    session.commit()
    return PricePointOut.model_validate(row)


@router.post("/api/refresh-prices")
def refresh_prices(session: SessionDep, household_id: int | None = None) -> list[dict[str, Any]]:
    """Serve the "Refresh prices" button.

    A single account's failure is an entry in the result, never an error response: the
    last stored price stands.
    """
    household = household_or_404(session, household_id)
    outcomes = prices.refresh_prices(session, household.id)
    session.commit()
    return [
        {
            "account_id": o.account_id,
            "account_name": o.account_name,
            "ok": o.ok,
            "value_eur": None if o.value_eur is None else str(o.value_eur),
            "error": o.error,
        }
        for o in outcomes
    ]
