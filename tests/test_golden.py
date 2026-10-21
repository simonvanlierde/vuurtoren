"""Golden-baseline drift tests and the country-neutral tax-regime seam."""

from __future__ import annotations

import ast
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

import vuurtoren.engine
from golden_plan import US_HOUSEHOLD, build_seeded_plan
from vuurtoren.engine import PlanInput, project
from vuurtoren.tax.nl.regime import NLTaxRegime

if TYPE_CHECKING:
    from vuurtoren.tax.regime import YearState

GOLDEN = Path(__file__).parent / "golden" / "baseline.json"
US_GOLDEN = Path(__file__).parent / "golden" / "us_baseline.json"
CHECKPOINTS = (12, 60, 360)


def test_the_baseline_projection_has_not_drifted(tmp_path: Path) -> None:
    """The seeded example household's projection matches the locked reference numbers."""
    expected = json.loads(GOLDEN.read_text())
    p = project(build_seeded_plan(tmp_path))

    for month in CHECKPOINTS:
        got = round(float(p.net_worth[0, month]), 2)
        assert got == pytest.approx(expected["net_worth"][str(month)], abs=1.0), (
            f"net worth at month {month} moved: {expected['net_worth'][str(month)]} -> {got}. "
            "If this change is intended, regenerate the golden file in its own commit."
        )
    fi_date = p.fire.fi_dates[0]
    assert expected["fi_date"] == (fi_date.isoformat() if fi_date else None)
    assert round(p.fire.fire_number, 2) == pytest.approx(expected["fire_number"], abs=1.0)
    assert round(float(p.tax_paid["investment_tax"][0].sum()), 2) == pytest.approx(
        expected["investment_tax_total"], abs=1.0
    )
    assert round(float(p.tax_paid["housing_adjustment"][0].sum()), 2) == pytest.approx(
        expected["housing_adjustment_total"], abs=1.0
    )
    assert round(float(p.tax_paid["withdrawal_tax"][0].sum()), 2) == pytest.approx(
        expected["withdrawal_tax_total"], abs=1.0
    )
    assert round(float(p.one_off_costs["transfer_tax"][0]), 2) == pytest.approx(
        expected["transfer_tax"], abs=1.0
    )


def test_the_us_person_baseline_has_not_drifted(tmp_path: Path) -> None:
    """The other half of the pair: a household that *does* have a US person.

    `baseline.json` proves the overlay reaches nobody it should not. This proves it still
    reaches the one it should — it is the only place a change to `tax/us/` shows up in a
    number at all, since the example household has no US person by design.

    What it does not cover: the § 904 carryforward and the § 1296 loss pool, neither of
    which binds in a deterministic projection where returns never fall. Those are unit
    tests' work (`tests/test_us_{ftc,pfic}.py`), not this fixture's.
    """
    expected = json.loads(US_GOLDEN.read_text())
    p = project(build_seeded_plan(tmp_path, US_HOUSEHOLD, buy_house=False))

    for month in CHECKPOINTS:
        got = round(float(p.net_worth[0, month]), 2)
        assert got == pytest.approx(expected["net_worth"][str(month)], abs=1.0), (
            f"US-household net worth at month {month} moved: "
            f"{expected['net_worth'][str(month)]} -> {got}. If intended, regenerate with "
            "`uv run python scripts/regenerate_golden.py us` in its own commit."
        )
    assert round(float(p.tax_paid["investment_tax"][0].sum()), 2) == pytest.approx(
        expected["investment_tax_total"], abs=1.0
    ), "the combined Dutch + US charge moved"
    assert round(float(p.tax_paid["withdrawal_tax"][0].sum()), 2) == pytest.approx(
        expected["withdrawal_tax_total"], abs=1.0
    )


def test_the_us_overlay_actually_reaches_the_us_fixture(tmp_path: Path) -> None:
    """The fixture is worth having only if the overlay is live in it.

    A baseline that happened to charge no US tax would lock in a number that could not
    move, and would go on passing after the overlay broke. So: strip the citizenship from
    the same household and the tax must fall.
    """
    plan = build_seeded_plan(tmp_path, US_HOUSEHOLD, buy_house=False)
    without = PlanInput(
        household=plan.household,
        people=[
            p.model_copy(update={"us_person": False, "us_filing_status": None}) for p in plan.people
        ],
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=plan.milestones,
        start=plan.start,
        assumptions=plan.assumptions,
    )

    charged = float(project(plan).tax_paid["investment_tax"].sum())
    unclaimed = float(project(without).tax_paid["investment_tax"].sum())

    assert charged > unclaimed, "the US fixture's overlay charges nothing — the baseline is inert"


def test_the_projection_is_reproducible(tmp_path: Path) -> None:
    """Projecting the same seeded plan twice yields byte-identical net worth arrays."""
    a = project(build_seeded_plan(tmp_path))
    b = project(build_seeded_plan(tmp_path))
    assert np.array_equal(a.net_worth, b.net_worth)


SRC = Path(vuurtoren.engine.__file__).parent
DUTCH_LAW = "vuurtoren.tax.nl"
MAY_IMPORT_DUTCH_LAW = {
    # The regime registry: it maps "NL" to NLTaxRegime, so naming the class is its job.
    "tax/regime.py",
}
"""Modules outside `tax/nl/` allowed to import from it. Everything else reaches Dutch law
through the `TaxRegime` protocol — the engine, the API, the other countries."""


def _imported_modules(path: Path) -> list[str]:
    """Every module `path` imports, at any scope, with relative imports resolved.

    `from x import y` yields both `x` and `x.y`, since `y` may be a submodule:
    `from vuurtoren.tax import nl` imports Dutch law without naming it in `module`.
    """
    package = ".".join(("vuurtoren", *path.relative_to(SRC).with_suffix("").parts[:-1]))
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join([*base, node.module] if node.module else base)
            else:
                module = node.module or ""
            found.append(module)
            found.extend(f"{module}.{a.name}" for a in node.names)
    return found


def _modules_outside_dutch_law() -> list[str]:
    return sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if not p.relative_to(SRC).as_posix().startswith("tax/nl/")
    )


@pytest.mark.parametrize(
    "module", [m for m in _modules_outside_dutch_law() if m not in MAY_IMPORT_DUTCH_LAW]
)
def test_nothing_outside_tax_nl_imports_dutch_tax_law(module: str) -> None:
    """Only `tax/nl/` and the regime registry name Dutch law, at any scope.

    Covers relative imports and `from vuurtoren.tax import nl` as well as the absolute
    form, because each of those once slipped past a check that read only `module`.
    """
    offenders = [
        m
        for m in _imported_modules(SRC / module)
        if m == DUTCH_LAW or m.startswith(f"{DUTCH_LAW}.")
    ]
    assert offenders == [], (
        f"{module} imports country-specific tax modules: {offenders}. "
        "Route it through the TaxRegime protocol instead."
    )


def test_the_import_check_covers_the_engine_and_its_allowlist_is_live() -> None:
    """Invariant 1 in CONTRIBUTING.md stays checked, and no allowlist entry is stale."""
    modules = _modules_outside_dutch_law()
    assert "engine.py" in modules
    assert "engine.py" not in MAY_IMPORT_DUTCH_LAW
    assert set(modules) >= MAY_IMPORT_DUTCH_LAW


class ZeroRegime:
    """A regime that taxes nothing, to prove a stub drops straight into the seam.

    Module scope rather than nested in the test: it is a protocol implementation, and
    nesting eleven methods inside a test function made the function itself read as
    complex when it is really three lines of assertion.
    """

    country = "ZZ"
    # A regime that models nothing has nothing it fails to model. Empty is a legitimate
    # answer to `limitations`, and this stub is where that is worth pinning.
    limitations: tuple[()] = ()

    def annual_investment_tax(self, s: YearState, cfg: object) -> np.ndarray:
        """No annual tax on holdings."""
        return np.zeros_like(s.home_value)

    def annual_housing_adjustment(self, s: YearState, cfg: object) -> np.ndarray:
        """No deduction and no imputed income."""
        return np.zeros_like(s.home_value)

    def purchase_costs(
        self,
        price: Decimal,
        *,
        buyer_age: int,
        own_occupancy: bool = True,
        starter_exemption_used: bool,
        mortgage_amount: Decimal,
        cfg: object,
    ) -> tuple[Decimal, bool]:
        """No transaction tax, and no starter exemption to consume."""
        return Decimal(0), False

    def state_pension_date(
        self,
        birth_date: date,
        *,
        growth: int,
    ) -> date:
        """A flat 67th birthday, ignoring growth."""
        return date(birth_date.year + 67, birth_date.month, birth_date.day)

    def gift_tax_free_amount(
        self,
        amount: Decimal,
        *,
        recipient_birth_date: date,
        gift_date: date,
        onetime_used: bool,
        cfg: object,
    ) -> Decimal:
        """Every gift is fully exempt."""
        return amount

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        year: int,
        cfg: object,
    ) -> np.ndarray:
        """Taking money out is never a taxable event."""
        return np.zeros_like(amount)

    def annual_basis_step_up(self, s: YearState, cfg: object) -> dict[str, np.ndarray]:
        """Nothing was taxed while held, so no basis is created."""
        return {}

    def sweep_excluded_treatments(self) -> frozenset[str]:
        """Nothing is off-limits as a sweep destination."""
        return frozenset()

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        """Nothing is taxed on the way out."""
        return frozenset()

    def valid_treatments(self) -> frozenset[str]:
        """The Dutch keys: it stands in for NL on a Dutch plan, taxing nothing."""
        from vuurtoren.tax.regime import regime_for  # noqa: PLC0415  # test-local stub

        return regime_for("NL").valid_treatments()

    def actual_return_treatments(self) -> frozenset[str]:
        """No actual-return base, so no tegenbewijs input."""
        return frozenset()


def test_a_zero_tax_regime_changes_only_the_tax_line(tmp_path: Path) -> None:
    """A stub regime must drop straight in — that is what makes the seam real."""
    plan = build_seeded_plan(tmp_path)
    nl = project(plan)
    zero = project(plan, regime=ZeroRegime())

    assert np.all(zero.tax_paid["investment_tax"] == 0.0)
    assert np.any(nl.tax_paid["investment_tax"] > 0.0)
    assert zero.net_worth[0, -1] > nl.net_worth[0, -1]


def test_every_seeded_account_has_a_treatment_the_regime_knows(tmp_path: Path) -> None:
    """Every account the example household seeds has a tax_treatment the NL regime recognizes."""
    plan = build_seeded_plan(tmp_path)
    known = NLTaxRegime().valid_treatments()
    unknown = [a.tax_treatment for a in plan.accounts if a.tax_treatment not in known]
    assert unknown == []
