"""Austrian wage arithmetic retains decimal precision across the extension boundary."""

from decimal import Decimal
from importlib import import_module

import pytest
from hypothesis import given, strategies as st

from vuurtoren.tax.at import income
from vuurtoren.tax.at.config import ATTaxConfig
from vuurtoren.tax.config import defaults_for

core = import_module("vuurtoren_core")


@given(cents=st.integers(-10_000, 1_000_000_000), extra=st.booleans())
def test_income(cents: int, *, extra: bool) -> None:
    """SV, the seven brackets, extra payments and net wages match to a cent."""
    cfg = defaults_for("AT", 2026, expect=ATTaxConfig)
    gross = Decimal(cents) / 100
    assert Decimal(core.at_social_insurance(str(gross), cfg)) == income.social_insurance(
        gross, cfg=cfg
    )
    assert Decimal(core.at_income_tax(str(gross), cfg)) == income.income_tax(gross, cfg=cfg)
    assert Decimal(core.at_sonderzahlung_tax(str(gross), cfg)) == income.sonderzahlung_tax(
        gross, cfg=cfg
    )
    assert Decimal(core.at_gross_to_net(str(gross), extra, cfg)) == income.gross_to_net(
        gross, cfg=cfg, sonderzahlungen=extra
    )


def test_invalid_decimal() -> None:
    """Malformed and overflowing amounts fail before financial arithmetic."""
    cfg = defaults_for("AT", 2026, expect=ATTaxConfig)
    for value in ("NaN", "not money", "1000000000001"):
        with pytest.raises(ValueError, match=r".+"):
            core.at_gross_to_net(value, sonderzahlungen=False, cfg=cfg)


@pytest.mark.parametrize("value", ["1E+3", "0E-28", "-1E+2"])
def test_scientific_decimal(value: str) -> None:
    """Valid Decimal notation is accepted at both value and parameter boundaries."""
    cfg = defaults_for("AT", 2026, expect=ATTaxConfig).model_copy(
        update={"social_insurance_ceiling": Decimal("1E+3")}
    )
    expected = income.gross_to_net(Decimal(value), cfg=cfg, sonderzahlungen=False)
    assert Decimal(core.at_gross_to_net(value, sonderzahlungen=False, cfg=cfg)) == expected


@pytest.mark.parametrize(
    "value",
    [
        "50000.12345678901234567890123",
        "100000.1234567890123456789012345",
        "0.001",
        "100.00000000000000000000000000001e0",
        "1000000000000.00000000000000000001e0",
        "0.000000000000000000000000000000001e2",
    ],
)
def test_fractional_cents_are_rejected(value: str) -> None:
    """Unsupported scalar precision is refused rather than silently rounded."""
    cfg = defaults_for("AT", 2026, expect=ATTaxConfig)
    for function in (core.at_income_tax, core.at_social_insurance, core.at_sonderzahlung_tax):
        with pytest.raises(ValueError, match="exact cents"):
            function(value, cfg)
    with pytest.raises(ValueError, match="exact cents"):
        core.at_gross_to_net(value, sonderzahlungen=False, cfg=cfg)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("social_insurance_ceiling", "50000.001", "2 decimal places"),
        ("income_rate_2", "0.123456", "4 decimal places"),
        ("sonderzahlung_share", "0.1234567890123456789", "18 decimal places"),
    ],
)
def test_unsupported_config_precision(field: str, value: str, message: str) -> None:
    """Experimental precision limits also apply to the supplied config."""
    cfg = defaults_for("AT", 2026, expect=ATTaxConfig).model_copy(update={field: Decimal(value)})
    with pytest.raises(ValueError, match=message):
        core.at_gross_to_net("50000", sonderzahlungen=True, cfg=cfg)
