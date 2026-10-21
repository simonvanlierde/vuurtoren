"""PolicyEngine/OpenFisca-style parameter YAML -> TaxConfigBase registrations.

Country-neutral, like tax/config.py: a country package ships one `parameters.yaml`
(keyed by its config class's field names) and calls load_country_parameters() at import
(see tax/nl/config.py). Each field block carries `description`, `unit` and a source
`reference`, plus dated `values` — the OpenFisca parameter shape, flattened to one file.
This repo's richer provenance (`status`, `verified_on`) rides alongside each value; both
the readable inline form and the stricter OpenFisca `metadata:` nesting are accepted.

The loader constructs `Decimal` straight from each scalar's raw text: a rate must never
round-trip through a C double (architectural invariant #4). The country's
`TaxConfigBase` subclass stays the internal representation and does all range/type
validation; passing it in is what keeps this module country-neutral.
"""

from __future__ import annotations

import importlib.resources
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import yaml

from vuurtoren.tax.config import Provenance, TaxConfigBase

# YAML keys, named so the shape is documented once.
_VALUE = "value"
_VALUES = "values"
_METADATA = "metadata"
_REFERENCE = "reference"
_HREF = "href"
_STATUS = "status"
_VERIFIED_ON = "verified_on"


class _DecimalSafeLoader(yaml.SafeLoader):
    """SafeLoader whose YAML floats become `Decimal` from the raw scalar text.

    A tax rate like 0.0235 must never round-trip through a C double (invariant #4).
    """


_DecimalSafeLoader.add_constructor(
    "tag:yaml.org,2002:float",
    lambda _loader, node: Decimal(node.value),  # node.value is the untouched source text
)


def _as_date(key: object) -> date:
    if isinstance(key, datetime):
        return key.date()
    if isinstance(key, date):
        return key
    return date.fromisoformat(str(key))


def _href_from_reference(ref: Any) -> str | None:  # noqa: ANN401  # raw YAML node
    """The first source URL in a `reference` value.

    Accepts a bare URL string, a list of URL strings, or a list of {title, href} maps
    (the PolicyEngine form).
    """
    if ref is None:
        return None
    for entry in ref if isinstance(ref, list) else [ref]:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict) and _HREF in entry:
            return str(entry[_HREF])
    return None


def _reference_href(container: dict[str, Any]) -> str | None:
    """The reference URL from a field block or a per-value map.

    Looked up at the top level or nested under `metadata` (the OpenFisca form).
    """
    nested = container.get(_METADATA)
    nested_ref = nested.get(_REFERENCE) if isinstance(nested, dict) else None
    return _href_from_reference(container.get(_REFERENCE)) or _href_from_reference(nested_ref)


def _value_and_metadata(entry: Any) -> tuple[Any, dict[str, Any]]:  # noqa: ANN401  # raw YAML node
    """Unpack one dated entry into (value, metadata).

    Accepts the readable inline form `{value: X, status: ..., verified_on: ...}` and the
    OpenFisca nested form `{value: X, metadata: {...}}`. A bare scalar has no metadata.
    """
    if isinstance(entry, dict) and _VALUE in entry:
        nested = entry.get(_METADATA)
        return entry[_VALUE], nested if isinstance(nested, dict) else entry
    return entry, {}


def parse_parameters[C: TaxConfigBase](text: str, config_cls: type[C]) -> dict[int, C]:
    """Build one `config_cls` per registered year from a country's parameter YAML.

    The document maps each figure's field name to a block of `description` / `unit` /
    `reference` / dated `values`. The registered years are the union of every value
    date's year; for each year, a field takes its latest value dated on or before that
    year's end (a field with no such value is an error). `config_cls`'s own validators
    enforce ranges and types.

    `config_cls` is what makes this loader country-neutral: it supplies the field set the
    document must match exactly, so the same code path loads NL and AT figures.
    """
    # _DecimalSafeLoader subclasses SafeLoader and only overrides the float constructor,
    # so it constructs no arbitrary objects.
    doc = yaml.load(text, Loader=_DecimalSafeLoader) or {}  # noqa: S506

    figure_fields = config_cls.figure_fields()
    fields = set(doc)
    missing = figure_fields - fields
    if missing:
        msg = f"parameters missing for field(s): {sorted(missing)}"
        raise ValueError(msg)
    stray = fields - figure_fields
    if stray:
        msg = f"parameter block(s) do not name a {config_cls.__name__} field: {sorted(stray)}"
        raise ValueError(msg)

    # field -> sorted [(effective_date, raw_value, per_value_metadata)], plus its
    # field-level reference for provenance.
    dated: dict[str, list[tuple[date, Any, dict[str, Any]]]] = {}
    field_reference: dict[str, str | None] = {}
    for field, block in doc.items():
        field_reference[field] = _reference_href(block)
        entries: list[tuple[date, Any, dict[str, Any]]] = []
        for raw_key, raw_entry in (block.get(_VALUES) or {}).items():
            value, meta = _value_and_metadata(raw_entry)
            entries.append((_as_date(raw_key), value, meta))
        dated[field] = sorted(entries, key=lambda t: t[0])

    years = sorted({d.year for entries in dated.values() for d, _, _ in entries})

    configs: dict[int, C] = {}
    for year in years:
        cutoff = date(year, 12, 31)
        payload: dict[str, Any] = {"year": year, "source_year": year}
        provenance: dict[str, Provenance] = {}
        for field, entries in dated.items():
            chosen = [t for t in entries if t[0] <= cutoff]
            if not chosen:
                msg = f"field {field!r} has no value effective for registered year {year}"
                raise ValueError(msg)
            _, value, meta = chosen[-1]
            payload[field] = value
            provenance[field] = _provenance(field, year, meta, field_reference[field])
        payload["provenance"] = provenance
        configs[year] = config_cls.model_validate(payload)
    return configs


def _provenance(field: str, year: int, meta: dict[str, Any], reference: str | None) -> Provenance:
    source = _reference_href(meta) or reference
    if source is None or _STATUS not in meta or _VERIFIED_ON not in meta:
        msg = (
            f"field {field!r} value for {year} is missing provenance "
            "(needs a reference href plus status and verified_on)"
        )
        raise ValueError(msg)
    return Provenance(status=meta[_STATUS], source=source, verified_on=meta[_VERIFIED_ON])


def load_country_parameters[C: TaxConfigBase](
    package: str, config_cls: type[C], filename: str = "parameters.yaml"
) -> dict[int, C]:
    """Load the `parameters.yaml` shipped inside an importable package."""
    text = (importlib.resources.files(package) / filename).read_text(encoding="utf-8")
    return parse_parameters(text, config_cls)
