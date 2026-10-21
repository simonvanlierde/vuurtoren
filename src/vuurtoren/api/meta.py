"""Read-only reference routes: the resolved tax config, the meta facts, the country list."""

from typing import Any

from fastapi import APIRouter, HTTPException

from vuurtoren.api.deps import SessionDep, get_or_404, household_or_404
from vuurtoren.seed import is_example_household
from vuurtoren.tables import HouseholdRow, ScenarioRow
from vuurtoren.tax.config import Unit, resolve_tax_config
from vuurtoren.tax.regime import regime_for, registered_countries

router = APIRouter()


@router.get("/api/tax-config")
def get_tax_config(
    session: SessionDep,
    year: int,
    country: str | None = None,
    scenario_id: int | None = None,
) -> dict[str, Any]:
    """Return the resolved tax config for a year, per field with its provenance.

    This is the tax panel's read model. A scenario_id resolves through that scenario's
    tax overrides, so overridden fields come back with status "user".
    """
    if country is None:
        country = household_or_404(session, None).tax_country
    overrides = None
    if scenario_id is not None:
        overrides = get_or_404(session, ScenarioRow, scenario_id).to_domain().overrides
    try:
        cfg = resolve_tax_config(country, year, overrides)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    # The `Money`/`Rate`/`Year` annotation already drives indexing and range validation.
    # Shipping it lets the panel format and range-check from the
    # same declaration instead of re-deriving one from field names.
    units = {name: unit.value for unit in Unit for name in type(cfg).fields_with_unit(unit)}
    fields = type(cfg).model_fields
    return {
        "country": country,
        "year": cfg.year,
        "source_year": cfg.source_year,
        "currency": type(cfg).currency,
        # The treatments an account may carry under this country's regime. The drawer
        # had an `nl.*` list baked in, which is simply wrong for an Austrian household.
        "valid_treatments": sorted(regime_for(country).valid_treatments()),
        "fields": {
            name: {
                "value": str(getattr(cfg, name)),
                "unit": units.get(name),
                # The prose next to the field declaration, so a figure the panel has no
                # group for still has a label rather than being dropped.
                "description": fields[name].description if name in fields else None,
                "status": prov.status,
                "source": prov.source,
                "verified_on": prov.verified_on.isoformat(),
            }
            for name, prov in sorted(cfg.provenance.items())
        },
    }


@router.get("/api/meta")
def get_meta(session: SessionDep) -> dict[str, Any]:
    """What a first-time reader needs in order to judge the numbers in front of them.

    Two facts that belong together because they answer the same question — "how much
    should I trust this?" — and nothing on the Plan surface was saying either. Whose
    numbers these are was marked only in the browser build, and what the model does not
    cover was written down only in the regime modules' docstrings.
    """
    household = session.query(HouseholdRow).order_by(HouseholdRow.id).first()
    country = household.tax_country if household is not None else None
    try:
        limitations = regime_for(country).limitations if country else ()
    except KeyError:
        # An unregistered country is a real state (the field was free text until the
        # select shipped). Say nothing rather than 500 the surface that reads the result.
        limitations = ()
    return {
        "example_data": is_example_household(session),
        "tax_country": country,
        "limitations": [
            {"direction": lim.direction, "nl": lim.nl, "en": lim.en} for lim in limitations
        ],
    }


@router.get("/api/tax-countries")
def list_tax_countries() -> list[str]:
    """The country codes a household may set as its tax country.

    The field was free text, so a typo passed CRUD validation and surfaced as a 404 from
    the projection rather than as an option that was never offered.
    """
    return registered_countries()
