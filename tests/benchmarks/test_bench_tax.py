"""CodSpeed benchmarks for Box 3, which the engine runs every year across all runs."""

from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.tax.nl.box3 import box3_tax_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for

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
