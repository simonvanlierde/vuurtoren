"""Country-neutral loader: policyengine-style parameter YAML -> a TaxConfigBase subclass.

Exercised against a *synthetic* schema and synthetic documents, never NL's, so the
loader's country-neutrality is proven rather than asserted: nothing in this module names
a Dutch figure, and a change that quietly re-coupled the loader to `NLTaxConfig` would
fail here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from vuurtoren.tax.config import Money, Rate, TaxConfigBase, Unit, Year
from vuurtoren.tax.parameters import parse_parameters


class _Config(TaxConfigBase):
    """A made-up country's schema: one figure per unit, and a second rate to vary."""

    wealth_rate: Rate
    second_rate: Rate
    allowance: Money
    switch_year: Year
    max_age: Year


_FIELDS = _Config.figure_fields()


def _valid_scalar(name: str) -> str:
    """A plausible in-range value for one field, as raw YAML scalar text."""
    if name in _Config.fields_with_unit(Unit.RATE):
        return "0.1"
    if name in _Config.fields_with_unit(Unit.MONEY):
        return "1000"
    return "2028" if name == "switch_year" else "40"


def _unit(name: str) -> str:
    for unit in Unit:
        if name in _Config.fields_with_unit(unit):
            return unit.value
    raise AssertionError(name)


def _block(name: str, values: dict[str, str], *, with_provenance: bool = True) -> str:
    """One field block: description / unit / reference / dated inline values."""
    lines = [
        f"{name}:",
        f"  description: test field {name}",
        f"  unit: {_unit(name)}",
        f"  reference: https://example.test/{name}",
        "  values:",
    ]
    for iso, scalar in values.items():
        if with_provenance:
            lines.append(f"    {iso}: {{value: {scalar}, status: final, verified_on: 2026-07-23}}")
        else:
            lines.append(f"    {iso}: {scalar}")
    return "\n".join(lines)


def _doc(
    *,
    overrides: dict[str, dict[str, str]] | None = None,
    omit: set[str] | None = None,
    extra: list[str] | None = None,
) -> str:
    """A full valid parameter document, customised.

    Applies per-field value overrides (field -> {iso: scalar}), omits named fields, and
    appends stray blocks (raw YAML strings).
    """
    overrides = overrides or {}
    omit = omit or set()
    blocks = [
        _block(name, overrides.get(name, {"2026-01-01": _valid_scalar(name)}))
        for name in sorted(_FIELDS)
        if name not in omit
    ]
    blocks.extend(extra or [])
    return "\n".join(blocks) + "\n"


def test_a_full_valid_doc_loads_one_config_per_year() -> None:
    """A complete document loads to one validated config for its year."""
    configs = parse_parameters(_doc(), _Config)
    assert set(configs) == {2026}
    cfg = configs[2026]
    assert cfg.year == 2026
    assert cfg.source_year == 2026
    assert cfg.wealth_rate == Decimal("0.1")


def test_decimal_values_never_round_trip_through_a_float() -> None:
    """0.0235 must load as exactly Decimal('0.0235'); plain safe_load would double it."""
    cfg = parse_parameters(_doc(overrides={"second_rate": {"2026-01-01": "0.0235"}}), _Config)[2026]
    assert cfg.second_rate == Decimal("0.0235")
    assert str(cfg.second_rate) == "0.0235"


def test_a_later_dated_value_registers_a_new_year() -> None:
    """A field's second dated value registers a new year; unchanged fields carry over."""
    configs = parse_parameters(
        _doc(overrides={"wealth_rate": {"2026-01-01": "0.36", "2027-01-01": "0.40"}}), _Config
    )
    assert set(configs) == {2026, 2027}
    assert configs[2026].wealth_rate == Decimal("0.36")
    assert configs[2027].wealth_rate == Decimal("0.40")
    # Fields without a 2027 value fall back to their latest value dated <= 2027.
    assert configs[2027].second_rate == configs[2026].second_rate


def test_a_field_with_no_value_for_a_registered_year_is_rejected() -> None:
    """A field with no value for a registered year is rejected.

    wealth_rate only has a 2027 value; 2026 is registered from the other fields, so
    wealth_rate has nothing dated <= 2026 -> ValueError naming field and year.
    """
    with pytest.raises(ValueError, match=r"wealth_rate.*2026"):
        parse_parameters(_doc(overrides={"wealth_rate": {"2027-01-01": "0.40"}}), _Config)


def test_a_missing_field_is_rejected() -> None:
    """A document missing one field's block fails, naming the missing field."""
    with pytest.raises(ValueError, match="wealth_rate"):
        parse_parameters(_doc(omit={"wealth_rate"}), _Config)


def test_a_stray_block_is_rejected() -> None:
    """A top-level key that is not a field of the config class fails, naming the block."""
    with pytest.raises(ValueError, match="not_a_field"):
        parse_parameters(_doc(extra=["not_a_field:\n  values:\n    2026-01-01: 1"]), _Config)


def test_provenance_is_built_from_reference_and_value_metadata() -> None:
    """Each field's provenance takes the reference href plus per-value status/date."""
    cfg = parse_parameters(_doc(), _Config)[2026]
    p = cfg.provenance["wealth_rate"]
    assert p.source == "https://example.test/wealth_rate"
    assert p.status == "final"
    assert p.verified_on == date(2026, 7, 23)


def test_a_value_missing_provenance_metadata_is_rejected() -> None:
    """A bare-scalar value with no status/verified_on fails, naming the field."""
    doc = _doc(
        omit={"wealth_rate"},
        extra=[_block("wealth_rate", {"2026-01-01": "0.1"}, with_provenance=False)],
    )
    with pytest.raises(ValueError, match="wealth_rate"):
        parse_parameters(doc, _Config)


def test_int_fields_stay_int() -> None:
    """Year-annotated figures load as int, not Decimal."""
    cfg = parse_parameters(_doc(), _Config)[2026]
    assert isinstance(cfg.switch_year, int)
    assert cfg.switch_year == 2028
    assert isinstance(cfg.max_age, int)


def test_a_rate_outside_zero_to_one_is_rejected() -> None:
    """`Rate` annotation drives the range check, so an out-of-range rate fails by name."""
    with pytest.raises(ValueError, match="wealth_rate"):
        parse_parameters(_doc(overrides={"wealth_rate": {"2026-01-01": "1.5"}}), _Config)


def test_the_loader_takes_any_config_class_not_just_the_dutch_one() -> None:
    """The loader is parameterised by config class, so a second country can use it.

    This is the country-neutrality claim made concrete: a schema sharing no field name
    with `_Config` (or with NL) loads through the same code path. Before the schema split
    the loader validated against a hard-coded `TaxConfig`, so any other country's
    document was rejected as entirely stray blocks.
    """

    class _ATLikeConfig(TaxConfigBase):
        kest_rate: Rate
        pension_age: Year

    doc = (
        "kest_rate:\n"
        "  description: KESt on investment income.\n"
        "  unit: /1\n"
        "  reference: https://example.test/kest\n"
        "  values:\n"
        "    2026-01-01: {value: 0.275, status: final, verified_on: 2026-07-23}\n"
        "pension_age:\n"
        "  description: Statutory pension age.\n"
        "  unit: year\n"
        "  reference: https://example.test/pension\n"
        "  values:\n"
        "    2026-01-01: {value: 65, status: final, verified_on: 2026-07-23}\n"
    )
    cfg = parse_parameters(doc, _ATLikeConfig)[2026]
    assert cfg.kest_rate == Decimal("0.275")
    assert isinstance(cfg.pension_age, int)
    assert cfg.provenance["kest_rate"].source == "https://example.test/kest"


def test_openfisca_nested_metadata_form_is_accepted() -> None:
    """The stricter {value, metadata: {...}} nesting parses as well as the inline form."""
    nested = (
        "wealth_rate:\n"
        "  description: nested\n"
        "  metadata:\n"
        "    unit: /1\n"
        "    reference: https://nested.test/wealth\n"
        "  values:\n"
        "    2026-01-01:\n"
        "      value: 0.36\n"
        "      metadata:\n"
        "        status: final\n"
        "        verified_on: 2026-07-23\n"
    )
    cfg = parse_parameters(_doc(omit={"wealth_rate"}, extra=[nested]), _Config)[2026]
    assert cfg.wealth_rate == Decimal("0.36")
    assert cfg.provenance["wealth_rate"].source == "https://nested.test/wealth"
