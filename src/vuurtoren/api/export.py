"""Export a household as one JSON document, and import one back."""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from vuurtoren.api.crud import check_treatment
from vuurtoren.api.deps import SessionDep, household_or_404, household_rows
from vuurtoren.api.schemas import ImportDocument, PricePointOut
from vuurtoren.tables import (
    AccountRow,
    CashFlowRow,
    HouseholdRow,
    MilestoneRow,
    PersonRow,
    PricePointRow,
    ScenarioRow,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from vuurtoren import domain

router = APIRouter()

# The export document's format version. Import reads it and refuses anything else, so a
# stored document stays a stable interchange rather than a backup blob tied to one build.
EXPORT_VERSION = 1


def _export_household(session: Session, household_id: int | None) -> dict[str, Any]:
    household_row = household_or_404(session, household_id)
    hh_id = household_row.id
    account_rows = household_rows(session, AccountRow, hh_id)
    account_ids = [a.id for a in account_rows]
    price_points = (
        session.query(PricePointRow)
        .filter(PricePointRow.account_id.in_(account_ids))
        .order_by(PricePointRow.id)
        .all()
        if account_ids
        else []
    )
    return {
        "version": EXPORT_VERSION,
        "household": household_row.to_domain().model_dump(mode="json"),
        "people": [
            r.to_domain().model_dump(mode="json") for r in household_rows(session, PersonRow, hh_id)
        ],
        "accounts": [r.to_domain().model_dump(mode="json") for r in account_rows],
        "price_points": [
            PricePointOut.model_validate(r).model_dump(mode="json") for r in price_points
        ],
        "cash_flows": [
            r.to_domain().model_dump(mode="json")
            for r in household_rows(session, CashFlowRow, hh_id)
        ],
        "milestones": [
            r.to_domain().model_dump(mode="json")
            for r in household_rows(session, MilestoneRow, hh_id)
        ],
        "scenarios": [
            r.to_domain().model_dump(mode="json")
            for r in household_rows(session, ScenarioRow, hh_id)
        ],
    }


@router.get("/api/export")
def export_household(session: SessionDep, household_id: int | None = None) -> dict[str, Any]:
    """Return one household and everything hanging off it as a single JSON document."""
    return _export_household(session, household_id)


@router.post("/api/import", status_code=201)
def import_household(doc: ImportDocument, session: SessionDep) -> dict[str, Any]:
    """Load a whole household from an export document.

    Ids are preserved verbatim, which keeps every foreign key valid without remapping —
    including the ones buried in milestone `params` and scenario `overrides` dict-keys.
    That makes the target an *empty* database: the browser build opens one each session
    and a restore starts clean, so a colliding id is refused with 409 rather than merged.
    NOTE: preserve-ids-into-empty-DB. Merging into a populated database would mean
    remapping every id (and rewriting those embedded references) — the reason it 409s.
    """
    if doc.version != EXPORT_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported export version {doc.version}; this build reads {EXPORT_VERSION}",
        )

    # Import writes accounts straight to the table, bypassing the create/update gate, so
    # it runs the same check itself — before the collision check, because a malformed
    # document is wrong whatever the target database holds.
    for account in doc.accounts:
        check_treatment(doc.household.tax_country, account.tax_treatment)

    incoming: dict[str, tuple[type[Any], list[int]]] = {
        "household": (HouseholdRow, [doc.household.id]),
        "person": (PersonRow, [p.id for p in doc.people]),
        "account": (AccountRow, [a.id for a in doc.accounts]),
        "price_point": (PricePointRow, [pp.id for pp in doc.price_points]),
        "cash_flow": (CashFlowRow, [c.id for c in doc.cash_flows]),
        "milestone": (MilestoneRow, [m.id for m in doc.milestones]),
        "scenario": (ScenarioRow, [s.id for s in doc.scenarios]),
    }
    for label, (row_cls, ids) in incoming.items():
        if ids and session.query(row_cls.id).filter(row_cls.id.in_(ids)).first() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"a {label} with an imported id exists; import into an empty database",
            )

    # These tables carry ForeignKey columns but no ORM relationship(), so the unit of
    # work cannot order a bulk insert itself. Flush each level before the rows that
    # reference it, or SQLite's per-row FK check fails.
    session.add(HouseholdRow(**doc.household.model_dump()))
    session.flush()
    session.add_all(PersonRow(**p.model_dump()) for p in doc.people)
    session.flush()  # people before accounts, which reference owner_person_id
    session.add_all(AccountRow(**a.model_dump()) for a in doc.accounts)
    session.flush()
    session.add_all(PricePointRow(**pp.model_dump()) for pp in doc.price_points)
    session.add_all(CashFlowRow(**c.model_dump()) for c in doc.cash_flows)
    session.add_all(_milestone_row(m) for m in doc.milestones)
    session.add_all(_scenario_row(s) for s in doc.scenarios)
    session.commit()

    return {
        "household_id": doc.household.id,
        "imported": {
            "people": len(doc.people),
            "accounts": len(doc.accounts),
            "price_points": len(doc.price_points),
            "cash_flows": len(doc.cash_flows),
            "milestones": len(doc.milestones),
            "scenarios": len(doc.scenarios),
        },
    }


def _milestone_row(m: domain.Milestone) -> MilestoneRow:
    """Build a MilestoneRow, storing `params` as the JSON-safe dict the column holds."""
    data = m.model_dump()
    data["params"] = m.params.model_dump(mode="json")
    return MilestoneRow(**data)


def _scenario_row(s: domain.Scenario) -> ScenarioRow:
    """Build a ScenarioRow, storing `overrides` as the JSON-safe dict the column holds."""
    data = s.model_dump()
    data["overrides"] = s.overrides.model_dump(mode="json")
    return ScenarioRow(**data)


@router.delete("/api/households/{household_id}/all", status_code=204)
def delete_household_and_everything(household_id: int, session: SessionDep) -> None:
    """Delete one household and every row that hangs off it, leaving import a clean target.

    The plain household DELETE refuses while people or accounts still reference it. This
    is the way out of the example household: start empty, or import a saved export.
    Dependants go first, in the reverse of import's insert order, for the FK checks.
    """
    hh_id = household_or_404(session, household_id).id
    account_ids = [a for (a,) in session.query(AccountRow.id).filter_by(household_id=hh_id)]
    if account_ids:
        session.query(PricePointRow).filter(PricePointRow.account_id.in_(account_ids)).delete()
    for row_cls in (CashFlowRow, MilestoneRow, ScenarioRow, AccountRow, PersonRow):
        session.query(row_cls).filter_by(household_id=hh_id).delete()
    session.query(HouseholdRow).filter_by(id=hh_id).delete()
    session.commit()
