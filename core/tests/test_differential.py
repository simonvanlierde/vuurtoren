"""Generated agreement checks against the Python engine retained during the port."""

from decimal import Decimal
from importlib import import_module

import numpy as np
import pytest
from hypothesis import given, strategies as st
from numpy.testing import assert_allclose

from vuurtoren.tax.nl import box1, box3
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for

core = import_module("vuurtoren_core")

# Engine arrays are finite euro amounts. One microcent permits float64 arithmetic order.
_AMOUNTS = st.lists(st.integers(min_value=0, max_value=100_000_000), min_size=1, max_size=20)


def config() -> NLTaxConfig:
    """Use the same exact-decimal parameter loader as the production engine."""
    return defaults_for("NL", 2026, expect=NLTaxConfig)


@given(amounts=_AMOUNTS, partners=st.booleans())
def test_forfaitair(amounts: list[int], *, partners: bool) -> None:
    """Taxable income agrees across asset mixes, debt and allowances."""
    bank = np.asarray(amounts, dtype=float) / 100
    investments, debt = bank[::-1], bank / 2
    cfg = config()
    expected = box3.forfaitair_income_array(
        bank, investments, debt, fiscal_partners=partners, cfg=cfg
    )
    actual = core.forfaitair_income_array(bank, investments, debt, partners, cfg)
    assert_allclose(np.asarray(actual), expected, rtol=0, atol=1e-8, strict=True)


@given(amounts=_AMOUNTS, partners=st.booleans())
def test_wwr_carry(amounts: list[int], *, partners: bool) -> None:
    """Loss creation, use and untouched carry match the reference."""
    returns = np.asarray(amounts, dtype=float) / 100 - 100_000
    pool = np.abs(returns[::-1])
    cfg = config()
    expected = box3.wwr_loss_carry(returns, pool, fiscal_partners=partners, cfg=cfg)
    actual = core.wwr_loss_carry(returns, pool, partners, cfg)
    assert_allclose(np.asarray(actual), expected, rtol=1e-14, atol=1e-8, strict=True)


@given(amounts=_AMOUNTS, share=st.sampled_from([0.0, 0.25, 0.5, 0.75, 1.0]))
def test_box1(amounts: list[int], share: float) -> None:
    """Both AOW schedules and their transition match the reference."""
    income = np.asarray(amounts, dtype=float) / 100
    labour = income[::-1]
    cfg = config()
    expected = box1.box1_tax_array(income, labour_income=labour, aow_share=share, cfg=cfg)
    actual = core.box1_tax_array(income, labour, share, cfg)
    assert_allclose(np.asarray(actual), expected, rtol=1e-14, atol=1e-8, strict=True)


def test_shapes() -> None:
    """Mismatched arrays fail at the extension boundary."""
    with pytest.raises(ValueError, match="same number of runs"):
        core.forfaitair_income_array([1.0], [], [1.0], fiscal_partners=False, cfg=config())


@given(amounts=_AMOUNTS, partners=st.booleans(), future=st.booleans(), elect=st.booleans())
def test_box3(amounts: list[int], *, partners: bool, future: bool, elect: bool) -> None:
    """Both regimes preserve election, allowance, carry and cent-rounding behavior."""
    bank = np.asarray(amounts, dtype=float) / 100
    investments, debt = bank[::-1], bank / 2
    actual_return = investments - bank
    pool = bank / 4
    cfg = config()
    year = 2028 if future else 2026
    expected = box3.box3_tax_array(
        bank,
        investments,
        debt,
        actual_return,
        year=year,
        fiscal_partners=partners,
        cfg=cfg,
        elect=elect,
        loss_carry=pool,
    )
    actual = core.box3_tax_array(
        bank, investments, debt, actual_return, year, partners, cfg, elect, pool
    )
    assert_allclose(np.asarray(actual), expected, rtol=0, atol=1e-8, strict=True)


def test_missing_return() -> None:
    """A missing actual return cannot become a proven zero in the future regime."""
    with pytest.raises(ValueError, match="regime B requires actual_return"):
        core.box3_tax_array([0.0], [0.0], [0.0], None, 2028, fiscal_partners=False, cfg=config())


def test_reversed_bracket_override() -> None:
    """An individually valid threshold override must not panic in a compiled kernel."""
    cfg = config().model_copy(update={"box1_bracket_1_to": Decimal(100_000)})
    income = np.array([10_000.0, 80_000.0, 120_000.0])
    expected = box1.box1_tax_array(income, labour_income=income, aow_share=0.0, cfg=cfg)
    actual = core.box1_tax_array(income, income, 0.0, cfg)
    assert_allclose(np.asarray(actual), expected, rtol=1e-14, atol=1e-8, strict=True)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input(value: float) -> None:
    """Reject invalid arrays before numerical operations enter the core."""
    with pytest.raises(ValueError, match="finite values"):
        core.box1_tax_array([value], [0.0], 0.0, config())


def test_empty_and_absent_carry() -> None:
    """Empty runs and an absent initial WWR pool preserve their distinct meanings."""
    cfg = config()
    assert core.box1_tax_array([], [], 0.0, cfg) == []
    actual_return = np.array([-1_000.0, 10_000.0])
    expected = box3.wwr_loss_carry(actual_return, None, fiscal_partners=False, cfg=cfg)
    actual = core.wwr_loss_carry(actual_return, None, fiscal_partners=False, cfg=cfg)
    assert_allclose(np.asarray(actual), expected, rtol=0, atol=1e-8, strict=True)
