"""Country-neutral tax config schema and resolution.

`TaxConfigBase` carries the machinery every country needs — the year stamps, the
provenance map, inflation indexing, and range validation — and nothing else. A country's
*figures* are fields on its own subclass (`tax/nl/config.py`'s `NLTaxConfig`), because no
two countries share a tax schema: Austria has no `box3_rate` and the Netherlands has no
`kest_rate`. Each subclass registers itself into `TAX_CONFIG` at import time.

Fields declare what they denominate by annotation — `Money`, `Rate`, `Year` — rather than
by being listed in a frozenset kept in step by hand. Indexing scales `Money`, the
validator range-checks `Rate`, and `/api/tax-config` ships the matching unit, all from
the one declaration next to the field.
"""

import importlib
from datetime import date
from decimal import Decimal
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Self, overload

from pydantic import BaseModel, ConfigDict, model_validator

from vuurtoren.domain import ScenarioOverrides

if TYPE_CHECKING:
    from vuurtoren.domain import TaxOverrides

Status = Literal["final", "provisional", "proposed", "user"]


class Unit(Enum):
    """What a figure denominates.

    The value is its OpenFisca `unit:` string, except for `MONEY` — money's unit names a
    currency, and which currency depends on the country, so `TaxConfigBase.currency`
    supplies it (`currency-<code>` in the parameter files).
    """

    MONEY = "currency"
    RATE = "/1"
    YEAR = "year"


class _NotIndexed:
    """Marker: this money figure is fixed in nominal terms and `indexed()` skips it.

    A marker beside `Unit.MONEY` rather than a rival unit, because such a figure *is*
    money for every other purpose — it is range-checked as money and exported with a
    currency unit. Only indexation differs, so only indexation should have to know.
    """


Money = Annotated[Decimal, Unit.MONEY]
"""A currency-denominated amount. Inflation indexing scales these; nothing else."""

FixedMoney = Annotated[Decimal, Unit.MONEY, _NotIndexed]
"""A currency amount that inflation indexing must leave alone.

For a threshold a legislature fixed in nominal terms and never indexed. The US net
investment income tax thresholds (IRC § 1411(b)) are the reason this exists: they have
stood at $200,000 and $250,000 since 2013 because no statute moves them, so scaling them
with a household's inflation assumption would turn a threshold real incomes drift across
into one they never reach — understating the tax, increasingly, for a whole projection.

If a figure is merely *not yet* indexed, it is `Money`. This is for figures whose statute
contains no indexing mechanism at all.
"""

Rate = Annotated[Decimal, Unit.RATE]
"""A dimensionless rate, validated into [0, 1]."""

Year = Annotated[int, Unit.YEAR]
"""A whole number of years — a calendar year or an age."""

# Structural fields every config carries. Everything else on a subclass is a figure, and
# the loader requires the country's parameter file to supply exactly those.
_STRUCTURAL = frozenset({"year", "source_year", "provenance"})


@cache
def _fields_with_unit(cls: type[TaxConfigBase], unit: Unit) -> frozenset[str]:
    """The fields of `cls` annotated with `unit`. Cached — the validator runs hot."""
    return frozenset(name for name, field in cls.model_fields.items() if unit in field.metadata)


@cache
def _indexable_money(cls: type[TaxConfigBase]) -> frozenset[str]:
    """Money fields inflation may scale — every `Money` field that is not `FixedMoney`."""
    return frozenset(
        name
        for name in _fields_with_unit(cls, Unit.MONEY)
        if _NotIndexed not in cls.model_fields[name].metadata
    )


class Provenance(BaseModel):
    """Where one figure came from, how settled it is, and when it was last checked."""

    model_config = ConfigDict(frozen=True)

    status: Status
    source: str
    verified_on: date


class TaxConfigBase(BaseModel):
    """The machinery behind one country's figures for one year.

    Frozen, and every figure is mirrored by a `provenance` entry — a rate without a
    source and a verification date is a rate nobody can audit. Subclasses add the
    figures; this class never names one.
    """

    model_config = ConfigDict(frozen=True)

    year: int
    source_year: int
    """The year the shipped figures are actually for. `defaults_for` stamps `year` with
    the requested year when it reuses the latest known rules, and inflation indexing
    must run from here, not from the projection start: a future shipped config already
    carries its own indexation."""

    provenance: dict[str, Provenance]

    @classmethod
    def figure_fields(cls) -> frozenset[str]:
        """The country's figures — every field that is not structural machinery."""
        return frozenset(cls.model_fields) - _STRUCTURAL

    currency: ClassVar[str] = "EUR"
    """The currency this country's money figures are denominated in.

    A class attribute rather than a `Unit` value: "is money" and "which money" are
    different facts, and folding them together would need one `Unit` member per currency.
    Only the US set is not EUR.
    """

    @classmethod
    def fields_with_unit(cls, unit: Unit) -> frozenset[str]:
        """The figures denominated in `unit`, from their `Money`/`Rate`/`Year` annotation."""
        return _fields_with_unit(cls, unit)

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        for name in self.fields_with_unit(Unit.RATE):
            value = getattr(self, name)
            if not (Decimal(0) <= value <= Decimal(1)):
                msg = f"{name}={value} is not a rate in [0, 1]"
                raise ValueError(msg)
        for name in self.fields_with_unit(Unit.MONEY):
            if getattr(self, name) < 0:
                msg = f"{name} must not be negative"
                raise ValueError(msg)
        if not (1900 <= self.year <= 2200):
            msg = f"year={self.year} is implausible"
            raise ValueError(msg)
        return self

    def in_currency(self, rate: Decimal) -> Self:
        """Every money figure translated at `rate`, expressed as target-per-source unit.

        For the US set that is euros per dollar: a $132,900 exclusion limit at 0.851
        becomes €113,098. Rates, years and provenance are untouched — a rate is
        dimensionless and does not translate.

        **Unlike `indexed`, this scales `FixedMoney` too.** The two skip-lists are not the
        same list, and conflating them would be a bug in either direction. A figure
        Congress never indexes is still denominated in dollars, so it must be converted;
        what `_NotIndexed` says is that inflation leaves it alone, not that arithmetic
        does.

        `currency` is a `ClassVar` and still reads `"USD"` on the result — this returns a
        working copy for one year's arithmetic, never something to export or ship.
        """
        patch: dict[str, Any] = {
            name: getattr(self, name) * rate for name in _fields_with_unit(type(self), Unit.MONEY)
        }
        # NOTE: shallow copy provenance, as indexed() does — the figures moved, but where
        # each came from and when it was checked did not.
        patch["provenance"] = dict(self.provenance)
        return self.model_copy(update=patch)

    def indexed(self, factor: Decimal) -> Self:
        """Scale currency allowances by `factor`. Rates and `FixedMoney` are untouched."""
        patch: dict[str, Any] = {
            name: getattr(self, name) * factor for name in _indexable_money(type(self))
        }
        # NOTE: shallow copy provenance dict to prevent aliasing the canonical instance
        patch["provenance"] = dict(self.provenance)
        return self.model_copy(update=patch)


# country -> year -> config. Populated by each country's tax/<cc>/config.py at import
# time (see tax/nl/config.py and tax/nl/__init__.py). Adding a country adds a
# registration there; nothing here changes.
TAX_CONFIG: dict[str, dict[int, TaxConfigBase]] = {}


@overload
def defaults_for(country: str, year: int) -> TaxConfigBase: ...
@overload
def defaults_for[C: TaxConfigBase](country: str, year: int, *, expect: type[C]) -> C: ...


def defaults_for(
    country: str, year: int, *, expect: type[TaxConfigBase] | None = None
) -> TaxConfigBase:
    """The shipped rules for (`country`, `year`).

    Years past the last researched one reuse the most recent known rules, stamped with
    the requested year. Provenance keeps its original verified_on, so the UI can show
    that a 2065 projection is running on rules verified in 2026.

    Args:
        country: ISO 3166-1 alpha-2 code, e.g. `"NL"`.
        year: The year to resolve figures for.
        expect: The country's config subclass. Pass it when you are about to read
            country-specific fields: it narrows the return type for the type checker and
            fails loudly if the registry holds another country's schema.

    Raises:
        KeyError: if no config is registered for `country`.
        TypeError: if `expect` is given and the registered config is not an instance.
    """
    try:
        by_year = TAX_CONFIG[country]
    except KeyError:
        # TAX_CONFIG is populated by import side-effect, so an unregistered country is
        # usually a missing import rather than an unsupported one. Run the import once
        # and retry: which module gets imported first varies by entrypoint, so a caller
        # that reached here through the API rather than through `tax/<cc>/regime.py`
        # would otherwise 404 a country the repo fully supports.
        try:
            importlib.import_module(f"vuurtoren.tax.{country.lower()}")
            by_year = TAX_CONFIG[country]
        except (ImportError, KeyError) as exc:
            msg = (
                f"no tax config registered for country {country!r} "
                f"(registered: {sorted(TAX_CONFIG)}). Adding a country means writing "
                f"tax/{country.lower()}/config.py; using one means importing "
                f"vuurtoren.tax.{country.lower()} so its registration runs."
            )
            # `from None` here hid a genuinely broken `tax/<cc>/__init__.py` behind
            # "no tax config registered", which sends you looking at the registry rather
            # than at the traceback of the import that actually failed.
            raise KeyError(msg) from exc
    # For years before any known config, fall back to the earliest known year.
    # This is unreachable today (only 2026 exists) but is a deliberate choice for robustness.
    known = max((y for y in by_year if y <= year), default=min(by_year))
    # NOTE: shallow copy provenance dict to prevent aliasing the canonical instance.
    # Callers may mutate the returned config's provenance (e.g., Task 4 sets status="user").
    cfg = by_year[known].model_copy(
        update={
            "year": year,
            "provenance": dict(by_year[known].provenance),
        }
    )
    return _narrow(cfg, expect, country)


def _narrow(cfg: TaxConfigBase, expect: type[TaxConfigBase] | None, country: str) -> TaxConfigBase:
    """Check a resolved config against the schema the caller expected."""
    if expect is not None and not isinstance(cfg, expect):
        msg = (
            f"tax config for {country!r} is {type(cfg).__name__}, not {expect.__name__} — "
            f"a caller reading {expect.__name__}'s fields was handed another country's schema"
        )
        raise TypeError(msg)
    return cfg


@overload
def resolve_tax_config(
    country: str, year: int, overrides: ScenarioOverrides | None = None
) -> TaxConfigBase: ...
@overload
def resolve_tax_config[C: TaxConfigBase](
    country: str, year: int, overrides: ScenarioOverrides | None = None, *, expect: type[C]
) -> C: ...


def resolve_tax_config(
    country: str,
    year: int,
    overrides: ScenarioOverrides | None = None,
    *,
    expect: type[TaxConfigBase] | None = None,
) -> TaxConfigBase:
    """Shipped defaults for (country, year), patched by this scenario's overrides.

    The patch builds a NEW provenance dict and revalidates from a dump; the shipped
    TAX_CONFIG entries are never touched, so scenarios cannot leak into each other or
    into later projections in the same process.

    Overrides are validated against the *country's own* schema, so an NL field name in an
    AT scenario is rejected by name rather than silently ignored.
    """
    base = defaults_for(country, year)
    patch = (overrides.tax.get(country, {}).get(year, {}) if overrides is not None else {}) or {}
    if not patch:
        return _narrow(base, expect, country)

    config_cls = type(base)
    unknown = set(patch) - set(config_cls.model_fields)
    if unknown:
        msg = f"unknown tax config field(s) for {country}: {sorted(unknown)}"
        raise KeyError(msg)

    provenance = {
        name: (
            Provenance(status="user", source=p.source, verified_on=p.verified_on)
            if name in patch
            else p
        )
        for name, p in base.provenance.items()
    }
    patched = config_cls.model_validate({**base.model_dump(), **patch, "provenance": provenance})
    return _narrow(patched, expect, country)


def check_tax_overrides(tax: TaxOverrides) -> None:
    """Fail on a tax override no projection could apply, before anything runs on it.

    Resolves every (country, year) the overrides name, so an unknown country, an unknown
    field and an out-of-range figure all fail here with `ValueError` rather than as a
    `KeyError` deep inside a projection.
    """
    overrides = ScenarioOverrides(tax=tax)
    for country, years in tax.items():
        for year in years:
            try:
                resolve_tax_config(country, year, overrides)
            except KeyError as e:
                raise ValueError(e.args[0] if e.args else str(e)) from e


def resolve_indexed_tax_config(
    country: str,
    year: int,
    overrides: ScenarioOverrides | None,
    *,
    inflation: float | None,
) -> TaxConfigBase:
    """The tax config for `year`, in that year's money; `inflation=None` skips indexing.

    Resolving without indexing is the bug this exists to prevent: the December wealth-tax
    step indexed its allowances and every other call site did not, so a gift or a house
    purchase decades out was measured against exemptions still quoted in 2026 euros.

    Whole years from the config's own source year, not months from the projection start:
    the shipped figures are already in source-year money, and a future shipped 2027 entry
    carries its own indexation — indexing from the projection start would double-count it.
    `FixedMoney` fields stay as enacted (see `indexed`).
    """
    cfg = resolve_tax_config(country, year, overrides)
    if inflation is None:
        return cfg
    years_since_config = max(0, year - cfg.source_year)
    if not years_since_config:
        return cfg
    factor = (1.0 + inflation) ** years_since_config
    return cfg.indexed(Decimal(str(factor)))
