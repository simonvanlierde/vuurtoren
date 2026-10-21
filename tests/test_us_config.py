"""US federal tax config: the shipped 2026 figures, and the threshold indexing must skip.

The figure set is data — asserting every value here would only restate `parameters.yaml`.
What is pinned instead is what a from-memory answer gets wrong: the top band that splits
between single and married-filing-separately, and the NIIT thresholds no statute indexes.
"""

import importlib.resources
from decimal import Decimal

from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.us.config import USTaxConfig


def _shipped() -> USTaxConfig:
    return defaults_for("US", 2026, expect=USTaxConfig)


def test_the_us_config_loads_with_provenance_on_every_field() -> None:
    """Every US figure is sourced and dated, like every other country's."""
    cfg = _shipped()

    assert cfg.niit_rate == Decimal("0.038")
    assert cfg.feie_limit == Decimal(132_900)
    for name in USTaxConfig.figure_fields():
        assert name in cfg.provenance, f"{name} ships without provenance"


def test_the_top_band_splits_between_single_and_married_filing_separately() -> None:
    """MFS tracks the unmarried schedule until the top band, then does not.

    Rev. Proc. 2025-32: the 37 % band opens at $640,600 for a single filer and at
    $384,350 for MFS. Treating MFS as "single" — the natural shortcut for a US citizen
    married to a non-US spouse, the main case — overstates the band's top by
    a quarter of a million dollars.
    """
    cfg = _shipped()

    assert cfg.ordinary_bracket_5_to_single == cfg.ordinary_bracket_5_to_mfs
    assert cfg.ordinary_bracket_6_to_single == Decimal(640_600)
    assert cfg.ordinary_bracket_6_to_mfs == Decimal(384_350)
    assert cfg.ordinary_rate_7 == Decimal("0.37")


def test_the_niit_thresholds_do_not_move_with_inflation() -> None:
    """Section 1411 fixes them in nominal dollars; nothing indexes them."""
    cfg = _shipped()

    indexed = cfg.indexed(Decimal(2))

    assert indexed.niit_threshold_mfs == cfg.niit_threshold_mfs
    assert indexed.niit_threshold_mfj == cfg.niit_threshold_mfj
    assert indexed.niit_threshold_single == cfg.niit_threshold_single
    assert indexed.feie_limit == cfg.feie_limit * 2
    assert indexed.standard_deduction_mfj == cfg.standard_deduction_mfj * 2


def test_the_shipped_parameter_file_says_dollars_and_never_euros() -> None:
    """The only non-EUR parameter file in the repo.

    A reader assuming euros misreads every figure by roughly 15 %, so the currency is
    stated on every money block's unit and once in prose at the top.
    """
    text = (importlib.resources.files("vuurtoren.tax.us") / "parameters.yaml").read_text(
        encoding="utf-8"
    )

    assert "currency-USD" in text
    assert "currency-EUR" not in text
    assert "USD" in text.split("\n\n")[0], "the header must state the currency in prose"
