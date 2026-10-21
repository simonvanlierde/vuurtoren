"""Generic CRUD over the household tables."""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from vuurtoren import domain
from vuurtoren.api.deps import SessionDep, get_or_404, household_or_404
from vuurtoren.api.schemas import (
    AccountIn,
    CashFlowIn,
    HouseholdIn,
    MilestoneIn,
    PersonIn,
    PricePointIn,
    PricePointOut,
    ScenarioIn,
)
from vuurtoren.tables import (
    AccountRow,
    CashFlowRow,
    HouseholdRow,
    MilestoneRow,
    PersonRow,
    PricePointRow,
    ScenarioRow,
)
from vuurtoren.tax.regime import regime_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel
    from sqlalchemy.orm import Session

router = APIRouter()


def _register_crud(
    router: APIRouter,
    path: str,
    name: str,
    row_cls: type[Any],
    in_schema: type[BaseModel],
    out_schema: type[BaseModel],
    to_domain: Callable[[Any], BaseModel] = lambda r: r.to_domain(),
    to_kwargs: Callable[[BaseModel], dict[str, Any]] | None = None,
    validate: Callable[[Any, Session], None] | None = None,
) -> None:
    """Wire POST/GET (list)/PUT/DELETE for one table under /api.

    `to_domain` maps a fetched row to the response schema (defaults to its own
    `to_domain()`); `to_kwargs` maps a validated request body to row constructor
    kwargs (defaults to `body.model_dump()` — overridden for the two JSON-column
    tables, where a nested Decimal/date has to become a JSON-safe string first).

    `validate` runs on create and update for a check pydantic cannot make on its own,
    because it needs the database — an account's `tax_treatment` is only meaningful
    against its household's tax country.
    """
    to_kwargs = to_kwargs or (lambda body: body.model_dump())

    # `in_schema`/`out_schema` are runtime variables holding a Pydantic model class, not
    # literal types, so ty cannot follow them into a parameter annotation or a
    # `list[...]` type-form. FastAPI only needs the runtime class to build the route.
    @router.post(f"/api/{path}", response_model=out_schema, status_code=201, name=f"create_{name}")
    def create(body: in_schema, session: SessionDep) -> BaseModel:  # ty: ignore[invalid-type-form]
        if validate is not None:
            validate(body, session)
        row = row_cls(**to_kwargs(body))
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_domain(row)

    @router.get(f"/api/{path}", response_model=list[out_schema], name=f"list_{name}")  # ty: ignore[invalid-type-form]
    def list_all(session: SessionDep) -> list[BaseModel]:
        rows = session.query(row_cls).order_by(row_cls.id).all()
        return [to_domain(r) for r in rows]

    @router.put(f"/api/{path}/{{item_id}}", response_model=out_schema, name=f"update_{name}")
    def update(
        item_id: int,
        body: in_schema,  # ty: ignore[invalid-type-form]
        session: SessionDep,
    ) -> BaseModel:
        row = get_or_404(session, row_cls, item_id)
        if validate is not None:
            validate(body, session)
        for k, v in to_kwargs(body).items():
            setattr(row, k, v)
        session.commit()
        session.refresh(row)
        return to_domain(row)

    @router.delete(f"/api/{path}/{{item_id}}", status_code=204, name=f"delete_{name}")
    def delete(item_id: int, session: SessionDep) -> None:
        session.delete(get_or_404(session, row_cls, item_id))
        session.commit()


def check_treatment(tax_country: str, tax_treatment: str) -> None:
    """Reject a tax_treatment the country's regime does not know.

    The field was free text, so `nl.box3_investmnet` saved cleanly and then taxed
    nothing at all — a silent zero rather than an error. An unregistered tax country is
    left alone: there is no regime to ask, and `/api/tax-countries` already stops that
    at the source.
    """
    try:
        valid = regime_for(tax_country).valid_treatments()
    except KeyError:
        return
    if tax_treatment not in valid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"tax_treatment {tax_treatment!r} is not one the "
                f"{tax_country} regime knows: {sorted(valid)}"
            ),
        )


def _validate_account(body: AccountIn, session: Session) -> None:
    """Gate an account create/update on its household's regime."""
    check_treatment(household_or_404(session, body.household_id).tax_country, body.tax_treatment)


_register_crud(router, "households", "household", HouseholdRow, HouseholdIn, domain.Household)
_register_crud(router, "people", "person", PersonRow, PersonIn, domain.Person)
_register_crud(
    router,
    "accounts",
    "account",
    AccountRow,
    AccountIn,
    domain.Account,
    validate=_validate_account,
)
_register_crud(router, "cash-flows", "cash_flow", CashFlowRow, CashFlowIn, domain.CashFlow)
_register_crud(
    router,
    "milestones",
    "milestone",
    MilestoneRow,
    MilestoneIn,
    domain.Milestone,
    to_kwargs=lambda body: {
        **body.model_dump(exclude={"params"}),
        "params": body.params.model_dump(mode="json"),  # ty: ignore[unresolved-attribute]
    },
)
_register_crud(
    router,
    "scenarios",
    "scenario",
    ScenarioRow,
    ScenarioIn,
    domain.Scenario,
    to_kwargs=lambda body: {
        **body.model_dump(exclude={"overrides"}),
        "overrides": body.overrides.model_dump(mode="json"),  # ty: ignore[unresolved-attribute]
    },
)
_register_crud(
    router,
    "price-points",
    "price_point",
    PricePointRow,
    PricePointIn,
    PricePointOut,
    PricePointOut.model_validate,
)
