"""CodSpeed benchmarks for the Dutch tax primitives the engine calls every year."""

from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.mortgage import annuity_payment
from vuurtoren.tax.nl.box1 import gross_to_net
from vuurtoren.tax.nl.box3 import box3_tax_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for
from vuurtoren.tax.nl.oneoff import transfer_tax

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture

CFG_2026 = defaults_for("NL", 2026, expect=NLTaxConfig)
CFG_2028 = defaults_for("NL", 2028, expect=NLTaxConfig)
N_RUNS = 10_000


def _wealth() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    bank = rng.uniform(0, 200_000, N_RUNS)
    investments = rng.uniform(0, 1_000_000, N_RUNS)
    debt = rng.uniform(0, 50_000, N_RUNS)
    actual = rng.normal(30_000, 40_000, N_RUNS)
    return bank, investments, debt, actual


def test_box3_forfaitair_10k_runs(benchmark: BenchmarkFixture) -> None:
    """Box 3 under the forfaitair regime, vectorised over 10,000 Monte Carlo runs."""
    bank, investments, debt, actual = _wealth()
    got = benchmark(
        lambda: box3_tax_array(
            bank, investments, debt, actual, year=2026, fiscal_partners=True, cfg=CFG_2026
        )
    )
    assert got.shape == (N_RUNS,)


def test_box3_werkelijk_rendement_10k_runs(benchmark: BenchmarkFixture) -> None:
    """Box 3 under the Wet werkelijk rendement, vectorised over 10,000 runs."""
    bank, investments, debt, actual = _wealth()
    got = benchmark(
        lambda: box3_tax_array(
            bank, investments, debt, actual, year=2028, fiscal_partners=True, cfg=CFG_2028
        )
    )
    assert got.shape == (N_RUNS,)


def test_box1_gross_to_net(benchmark: BenchmarkFixture) -> None:
    """Box 1 gross-to-net across a range of salaries."""
    salaries = [Decimal(g) for g in range(0, 250_000, 2_500)]

    def run() -> list[Decimal]:
        return [gross_to_net(g, cfg=CFG_2026) for g in salaries]

    assert len(benchmark(run)) == len(salaries)


def test_transfer_tax_and_annuity(benchmark: BenchmarkFixture) -> None:
    """The one-off purchase arithmetic: transfer tax plus the mortgage annuity."""
    prices = [Decimal(p) for p in range(200_000, 1_200_000, 10_000)]

    def run() -> Decimal:
        total = Decimal(0)
        for price in prices:
            duty, _ = transfer_tax(
                price,
                buyer_age=30,
                own_occupancy=True,
                starter_exemption_used=False,
                cfg=CFG_2026,
            )
            total += duty + annuity_payment(price, Decimal("0.04"), 360)
        return total

    assert benchmark(run) > 0
