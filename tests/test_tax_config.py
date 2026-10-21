"""NL tax config: shipped figures, provenance, indexing, and override resolution."""

import subprocess
import sys
from datetime import date
from decimal import Decimal

import pytest
from pydantic import Field, ValidationError

from vuurtoren.domain import ScenarioOverrides
from vuurtoren.tax.config import FixedMoney, Money, TaxConfigBase
from vuurtoren.tax.nl.config import (
    TAX_CONFIG,
    NLTaxConfig,
    Provenance,
    defaults_for,
    resolve_tax_config,
)


def _shipped(year: int) -> NLTaxConfig:
    """The canonical registry entry for `year`, narrowed to the Dutch schema.

    `TAX_CONFIG` is typed to the country-neutral base — reading a Dutch field off it
    needs the narrowing that production code gets from `defaults_for(..., expect=...)`.
    """
    cfg = TAX_CONFIG["NL"][year]
    assert isinstance(cfg, NLTaxConfig)
    return cfg


def test_2026_figures_match_the_spec() -> None:
    """The shipped 2026 NL tax figures match the verified values."""
    c = _shipped(2026)
    assert c.box3_rate == Decimal("0.36")
    assert c.box3_allowance_per_person == Decimal(59357)
    assert c.box3_debt_threshold_per_person == Decimal(3800)
    assert c.box3_forfait_bank == Decimal("0.0128")
    assert c.box3_forfait_investments == Decimal("0.06")
    assert c.box3_forfait_debt == Decimal("0.027")
    assert c.hra_max_rate == Decimal("0.3756")
    assert c.labour_credit_max == Decimal(5685)
    assert c.pension_withdrawal_rate == Decimal("0.3756")
    assert c.ewf_rate == Decimal("0.0035")
    assert c.ewf_high_rate == Decimal("0.0235")
    assert c.ewf_threshold == Decimal(1350000)
    assert c.transfer_tax_own_home_rate == Decimal("0.02")
    assert c.transfer_tax_general_rate == Decimal("0.08")
    assert c.starter_exemption_value_cap == Decimal(555000)
    assert c.starter_exemption_max_age == 35
    assert c.gift_exemption_onetime == Decimal(33129)
    assert c.gift_exemption_annual == Decimal(6908)
    assert c.regime_switch_year == 2028
    assert c.wwr_rate == Decimal("0.36")
    assert c.wwr_allowance_per_person == Decimal(1800)


def test_box1_rate_2_derived_fields_agree() -> None:
    """The three fields defined as the second Box 1 bracket rate stay equal.

    hra_max_rate and pension_withdrawal_rate are defined as box1_rate_2.
    Three parameter files now carry the figure, so their equality is enforced here in
    place of the shared `_BOX1_RATE_2` constant that used to bind them.
    """
    for year in TAX_CONFIG["NL"]:
        cfg = _shipped(year)
        assert cfg.hra_max_rate == cfg.box1_rate_2
        assert cfg.pension_withdrawal_rate == cfg.box1_rate_2


def test_every_field_has_provenance() -> None:
    """Every figure of every registered country carries dated, sourced provenance.

    Driven by each config's own schema, not a fixed field list, so a second country
    is held to the same standard the moment it registers.
    """
    for (_country, year), config in (
        ((c, y), cfg) for c, ys in TAX_CONFIG.items() for y, cfg in ys.items()
    ):
        for name in type(config).figure_fields():
            assert name in config.provenance, f"{year}.{name} has no provenance"
            p = config.provenance[name]
            assert p.source.startswith("http"), f"{year}.{name} source is not a URL"
            assert isinstance(p.verified_on, date)
            assert p.status in {"final", "provisional", "proposed", "user"}


def test_provisional_fields_are_marked_provisional() -> None:
    """Provisional, final, and proposed figures each carry the matching status."""
    p = TAX_CONFIG["NL"][2026].provenance
    assert p["box3_forfait_bank"].status == "provisional"
    assert p["box3_forfait_debt"].status == "provisional"
    assert p["box3_forfait_investments"].status == "final"
    assert p["wwr_rate"].status == "proposed"


def test_defaults_for_a_future_year_uses_the_latest_known_rules() -> None:
    """A year past the shipped figures falls back to the latest known rate."""
    c = defaults_for("NL", 2065, expect=NLTaxConfig)
    assert c.year == 2065
    assert c.box3_rate == _shipped(2026).box3_rate
    assert c.provenance["box3_rate"].verified_on == date(2026, 7, 23)


def test_defaults_for_a_far_year_keeps_the_source_year() -> None:
    """The engine indexes allowances from the year the shipped figures are for.

    So a reused config must say which year that was even when stamped with a later one.
    """
    c = defaults_for("NL", 2040, expect=NLTaxConfig)
    assert c.year == 2040
    assert c.source_year == 2026


def test_defaults_for_a_known_year_is_exact() -> None:
    """A year with shipped figures returns them exactly, with no indexing applied."""
    assert defaults_for("NL", 2026, expect=NLTaxConfig).box3_allowance_per_person == Decimal(59357)


def test_indexed_scales_money_amounts_but_not_rates() -> None:
    """Indexing scales money amounts by the given factor but leaves rates untouched."""
    c = defaults_for("NL", 2036, expect=NLTaxConfig).indexed(Decimal("1.5"))
    assert c.box3_allowance_per_person == Decimal("89035.50")
    assert c.box3_debt_threshold_per_person == Decimal("5700.00")
    assert c.wwr_allowance_per_person == Decimal("2700.00")
    assert c.box3_rate == Decimal("0.36")
    assert c.box3_forfait_investments == Decimal("0.06")


def test_config_is_frozen() -> None:
    """Config instances reject attribute assignment after construction."""
    with pytest.raises(ValidationError):
        TAX_CONFIG["NL"][2026].box3_rate = Decimal("0.40")  # ty: ignore[invalid-assignment]


def test_defaults_for_provenance_is_independent_copy() -> None:
    """Mutating provenance of defaults_for() result must not affect canonical TAX_CONFIG."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig)
    original_status = TAX_CONFIG["NL"][2026].provenance["box3_rate"].status

    # Mutate the returned config's provenance
    cfg.provenance["box3_rate"] = Provenance(
        status="user",
        source="test",
        verified_on=date(2026, 7, 23),
    )

    # Canonical TAX_CONFIG must not be affected
    assert TAX_CONFIG["NL"][2026].provenance["box3_rate"].status == original_status
    assert TAX_CONFIG["NL"][2026].provenance["box3_rate"].status != "user"


def test_indexed_provenance_is_independent_copy() -> None:
    """Mutating provenance of indexed() result must not affect canonical TAX_CONFIG."""
    cfg = defaults_for("NL", 2026, expect=NLTaxConfig).indexed(Decimal("1.5"))
    original_status = TAX_CONFIG["NL"][2026].provenance["box3_rate"].status

    # Mutate the returned config's provenance
    cfg.provenance["box3_rate"] = Provenance(
        status="user",
        source="test",
        verified_on=date(2026, 7, 23),
    )

    # Canonical TAX_CONFIG must not be affected
    assert TAX_CONFIG["NL"][2026].provenance["box3_rate"].status == original_status
    assert TAX_CONFIG["NL"][2026].provenance["box3_rate"].status != "user"


def test_provenance_is_frozen() -> None:
    """Provenance instances must be frozen (frozen=True enforced)."""
    p = Provenance(status="final", source="http://example.com", verified_on=date(2026, 7, 23))

    with pytest.raises(ValidationError):
        p.status = "user"  # ty: ignore[invalid-assignment]


def test_no_overrides_returns_the_defaults() -> None:
    """No override, or an empty one, resolves to the shipped defaults."""
    assert resolve_tax_config("NL", 2026, None, expect=NLTaxConfig) == defaults_for(
        "NL", 2026, expect=NLTaxConfig
    )
    assert resolve_tax_config("NL", 2026, ScenarioOverrides(), expect=NLTaxConfig) == defaults_for(
        "NL", 2026, expect=NLTaxConfig
    )


def test_a_sparse_patch_changes_only_the_patched_field() -> None:
    """A patch touching one field leaves every other field at its default."""
    o = ScenarioOverrides(tax={"NL": {2026: {"box3_rate": Decimal("0.40")}}})
    c = resolve_tax_config("NL", 2026, o, expect=NLTaxConfig)
    assert c.box3_rate == Decimal("0.40")
    assert (
        c.box3_allowance_per_person
        == defaults_for("NL", 2026, expect=NLTaxConfig).box3_allowance_per_person
    )


def test_a_patched_field_is_marked_user() -> None:
    """A patched field's provenance status flips to user; other fields stay final."""
    o = ScenarioOverrides(tax={"NL": {2026: {"box3_rate": Decimal("0.40")}}})
    c = resolve_tax_config("NL", 2026, o, expect=NLTaxConfig)
    assert c.provenance["box3_rate"].status == "user"
    assert c.provenance["box3_allowance_per_person"].status == "final"


def test_overrides_apply_to_the_requested_year_only() -> None:
    """An override scoped to one year leaves other years untouched."""
    o = ScenarioOverrides(tax={"NL": {2030: {"box3_rate": Decimal("0.40")}}})
    assert resolve_tax_config("NL", 2026, o, expect=NLTaxConfig).box3_rate == Decimal("0.36")
    assert resolve_tax_config("NL", 2030, o, expect=NLTaxConfig).box3_rate == Decimal("0.40")


def test_overrides_never_mutate_the_shipped_defaults() -> None:
    """Resolving an override never mutates the canonical TAX_CONFIG."""
    before_rate = _shipped(2026).box3_rate
    before_status = TAX_CONFIG["NL"][2026].provenance["box3_rate"].status

    patch = ScenarioOverrides(tax={"NL": {2026: {"box3_rate": Decimal("0.40")}}})
    resolve_tax_config("NL", 2026, patch, expect=NLTaxConfig)

    assert _shipped(2026).box3_rate == before_rate
    assert TAX_CONFIG["NL"][2026].provenance["box3_rate"].status == before_status
    assert (
        resolve_tax_config("NL", 2026, None, expect=NLTaxConfig).provenance["box3_rate"].status
        == "final"
    )


def test_two_scenarios_do_not_leak_into_each_other() -> None:
    """Two scenarios resolved from the same base config do not share mutable state."""
    a = resolve_tax_config(
        "NL",
        2026,
        ScenarioOverrides(tax={"NL": {2026: {"box3_rate": Decimal("0.40")}}}),
        expect=NLTaxConfig,
    )
    b = resolve_tax_config(
        "NL",
        2026,
        ScenarioOverrides(tax={"NL": {2026: {"box3_forfait_bank": Decimal("0.02")}}}),
        expect=NLTaxConfig,
    )
    assert a.box3_rate == Decimal("0.40")
    assert b.box3_rate == Decimal("0.36")
    assert b.provenance["box3_rate"].status == "final"


def test_an_unknown_field_is_rejected() -> None:
    """Patching a field name that does not exist on the country's schema raises."""
    with pytest.raises(KeyError):
        resolve_tax_config(
            "NL", 2026, ScenarioOverrides(tax={"NL": {2026: {"box3_taruf": Decimal("0.40")}}})
        )


def test_an_out_of_range_rate_is_rejected() -> None:
    """A rate override outside the valid fraction range is rejected by validation."""
    with pytest.raises(ValidationError):
        resolve_tax_config(
            "NL", 2026, ScenarioOverrides(tax={"NL": {2026: {"box3_rate": Decimal(36)}}})
        )


def test_a_negative_allowance_is_rejected() -> None:
    """A negative allowance override is rejected by validation."""
    with pytest.raises(ValidationError):
        resolve_tax_config(
            "NL",
            2026,
            ScenarioOverrides(tax={"NL": {2026: {"box3_allowance_per_person": Decimal(-1)}}}),
        )


# --- FixedMoney: a figure no statute indexes -------------------------------------------


class _FixedMoneyConfig(TaxConfigBase):
    """Throwaway schema exercising both kinds of money side by side."""

    an_indexed_allowance: Money = Field(description="An ordinary allowance.")
    a_fixed_threshold: FixedMoney = Field(description="A threshold nothing indexes.")

    currency = "USD"


def _both_kinds() -> _FixedMoneyConfig:
    return _FixedMoneyConfig(
        year=2026,
        source_year=2026,
        an_indexed_allowance=Decimal(1000),
        a_fixed_threshold=Decimal(200_000),
        provenance={
            "an_indexed_allowance": Provenance(
                status="final", source="x", verified_on=date(2026, 1, 1)
            ),
            "a_fixed_threshold": Provenance(
                status="final", source="y", verified_on=date(2026, 1, 1)
            ),
        },
    )


def test_a_fixed_money_field_survives_indexation() -> None:
    """A threshold Congress never indexes must not drift with the household's inflation.

    The US NIIT thresholds have stood at $200,000 and $250,000 since 2013 because no
    statute indexes them. Scaling them would turn a threshold real incomes drift across
    into one they never reach, understating US tax for the whole horizon.
    """
    cfg = _both_kinds()

    indexed = cfg.indexed(Decimal("1.5"))

    assert indexed.an_indexed_allowance == Decimal(1500)
    assert indexed.a_fixed_threshold == Decimal(200_000)


def test_a_fixed_money_field_is_still_range_checked() -> None:
    """It differs from Money in exactly one respect: indexing. Not in validation."""
    with pytest.raises(ValidationError):
        _FixedMoneyConfig(
            year=2026,
            source_year=2026,
            an_indexed_allowance=Decimal(1000),
            a_fixed_threshold=Decimal(-1),
            provenance={},
        )


def test_a_config_declares_its_own_currency() -> None:
    """US figures are USD. Every other country's are EUR, and the default stays EUR."""
    assert _FixedMoneyConfig.currency == "USD"
    assert NLTaxConfig.currency == "EUR"


def test_a_country_registers_itself_on_first_resolution() -> None:
    """`defaults_for` imports the country's package rather than failing on import order.

    Which module runs first depends on the entrypoint: a fresh process that reaches
    `/api/tax-config` before anything has touched `tax/nl/` used to get a KeyError for a
    country the repo fully supports. A subprocess is the only honest repro — inside this
    one the registration has long since run.
    """
    for country in ("NL", "AT"):
        subprocess.run(  # noqa: S603  # sys.executable and a literal -c, no user input
            [
                sys.executable,
                "-c",
                (
                    "from vuurtoren.tax.config import defaults_for;"
                    f"assert defaults_for({country!r}, 2026).year == 2026"
                ),
            ],
            check=True,
        )
    unknown = subprocess.run(  # sys.executable and a literal -c, no user input
        [
            sys.executable,
            "-c",
            "from vuurtoren.tax.config import defaults_for; defaults_for('ZZ', 2026)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert unknown.returncode != 0
    assert "no tax config registered" in unknown.stderr


def test_an_unregistered_country_keeps_the_import_failure_as_the_cause() -> None:
    """The KeyError chains what actually went wrong, rather than swallowing it.

    `from None` hid a genuinely broken `tax/<cc>/__init__.py` behind "no tax config
    registered for country 'NL'" — the one message that sends you looking at the
    registry rather than at the traceback of the import that failed.
    """
    with pytest.raises(KeyError) as excinfo:
        defaults_for("ZZ", 2026)
    assert isinstance(excinfo.value.__cause__, ImportError)
