"""Read-only steps from the planner's deterministic tax calculations."""

from typing import Literal

from pydantic import BaseModel

from vuurtoren.tax.config import Status, Unit


class TaxParameterUsed(BaseModel):
    """A resolved, possibly indexed or overridden figure used by a rule."""

    value: str
    unit: Unit | None
    source_year: int
    status: Status
    source: str
    sources: list[str]
    verified_on: str


class TaxStep(BaseModel):
    """One intermediate result and the sourced parameters behind it."""

    rule: str
    value: str
    unit: Literal["currency", "rate", "number"] = "currency"
    parameters: dict[str, TaxParameterUsed]


class TaxCalculation(BaseModel):
    """A taxpayer or housing calculation; Dutch rule names stay untranslated."""

    label: str
    person_id: int | None = None
    steps: list[TaxStep]


class TaxExplanationOut(BaseModel):
    """One closed tax year of the same deterministic plan as the chart."""

    year: int
    country: str
    first_month: str
    fiscal_partners: bool
    calculations: list[TaxCalculation]
    totals: dict[str, str]
    limitations: list[dict[str, str]]
