"""Box 3 against the Belastingdienst's own worked examples (golden files).

Each `tests/golden/box3/*.yaml` holds one published example: its source, the inputs and
the published figures. The Belastingdienst works in whole euros, rounded down, so each
engine figure is rounded down to the euro before the comparison. Partner examples
publish one partner's figures; `share` is that partner's part of the grondslag sparen en
beleggen, and the engine's household figure is scaled by it.

A published figure the engine does not reproduce carries an `xfail` reason in its file.
The engine is not adjusted to match: the reason says which side departs from the law.
Such a figure also pins the engine's own unrounded figure under `engine`, so a strict
xfail cannot hide a large shift: it still fails, and the pin catches the move.
"""

from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vuurtoren.tax.nl.box3 import box3_tax_array, forfaitair_income_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for

GOLDEN = Path(__file__).parent / "golden"
CFG_2026 = defaults_for("NL", 2026, expect=NLTaxConfig)


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


_OVERLAY_2025 = _load(GOLDEN / "box3_parameters_2025.yaml")
CFG = {
    2026: CFG_2026,
    2025: CFG_2026.model_copy(
        update={k: Decimal(v) for k, v in _OVERLAY_2025.items() if k.startswith("box3_")}
    ),
}
EXAMPLES = {p.stem: _load(p) for p in sorted((GOLDEN / "box3").glob("*.yaml"))}


def _cases(figure: str) -> list[Any]:
    return [
        pytest.param(
            slug,
            id=slug,
            marks=[pytest.mark.xfail(reason=ex["xfail"][figure], strict=True)]
            if figure in ex.get("xfail", {})
            else [],
        )
        for slug, ex in EXAMPLES.items()
        if figure in ex["published"]
    ]


def _arrays(ex: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The example's bank, investments and debt as one-run arrays."""
    inp = ex["inputs"]
    bank, investments, debt = (np.array([float(inp[k])]) for k in ("bank", "investments", "debt"))
    return bank, investments, debt


def _voordeel(ex: dict[str, Any]) -> Decimal:
    """The engine's forfaitair voordeel for the household, as the cents it computed."""
    got = forfaitair_income_array(
        *_arrays(ex), fiscal_partners=ex["fiscal_partners"], cfg=CFG[ex["tax_year"]]
    )
    return Decimal(repr(float(got[0])))


def _tax(ex: dict[str, Any], *, elect: bool = False) -> Decimal:
    """The engine's regime A Box 3 tax; `elect` applies the tegenbewijs."""
    actual = ex["inputs"].get("actual_return")
    got = box3_tax_array(
        *_arrays(ex),
        None if actual is None else np.array([float(actual)]),
        year=ex["tax_year"],
        fiscal_partners=ex["fiscal_partners"],
        cfg=CFG[ex["tax_year"]],
        elect=elect,
    )
    return Decimal(repr(float(got[0])))


def _to_euro(household: Decimal, ex: dict[str, Any]) -> int:
    return int((household * Decimal(ex["share"])).quantize(Decimal(1), rounding=ROUND_DOWN))


def test_every_golden_example_names_an_official_source() -> None:
    """Each golden file cites a belastingdienst.nl page and its retrieval date."""
    assert EXAMPLES
    for slug, ex in EXAMPLES.items():
        assert ex["source"].startswith("https://www.belastingdienst.nl/"), slug
        assert str(ex["retrieved"]) == "2026-10-12", slug
        assert ex["tax_year"] in CFG, slug


@pytest.mark.parametrize("slug", _cases("voordeel"))
def test_golden_voordeel_matches_the_published_example(slug: str) -> None:
    """The forfaitair voordeel uit sparen en beleggen matches the published figure."""
    ex = EXAMPLES[slug]
    assert _to_euro(_voordeel(ex), ex) == ex["published"]["voordeel"]


@pytest.mark.parametrize("slug", _cases("belasting"))
def test_golden_box3_tax_matches_the_published_example(slug: str) -> None:
    """The forfaitair Box 3 tax matches the published figure."""
    ex = EXAMPLES[slug]
    assert _to_euro(_tax(ex), ex) == ex["published"]["belasting"]


@pytest.mark.parametrize("slug", _cases("worth_reporting"))
def test_golden_tegenbewijs_election_matches_the_published_verdict(slug: str) -> None:
    """The engine elects the werkelijk rendement exactly when the example says it pays."""
    ex = EXAMPLES[slug]
    assert (_tax(ex, elect=True) < _tax(ex)) is ex["published"]["worth_reporting"]


_PINNED = [
    pytest.param(slug, figure, id=f"{slug}-{figure}")
    for slug, ex in EXAMPLES.items()
    for figure in ex.get("xfail", {})
]
_FIGURE = {"voordeel": _voordeel, "belasting": _tax}


def test_every_xfail_pins_the_engine_figure() -> None:
    """An xfail without a pin would let the engine drift anywhere unnoticed."""
    for slug, ex in EXAMPLES.items():
        assert set(ex.get("xfail", {})) == set(ex.get("engine", {})), slug


@pytest.mark.parametrize(("slug", "figure"), _PINNED)
def test_an_xfailed_example_holds_the_engine_figure_its_reason_states(
    slug: str, figure: str
) -> None:
    """Where the engine departs from a page, it departs by exactly the documented amount."""
    ex = EXAMPLES[slug]
    got = _FIGURE[figure](ex) * Decimal(ex["share"])
    assert abs(got - Decimal(ex["engine"][figure])) <= Decimal("0.01")
