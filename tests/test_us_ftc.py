"""The foreign tax credit: the § 904 limitation, and ten years of carryforward."""

import numpy as np
import pytest

from vuurtoren.tax.us.federal.ftc import CARRYFORWARD_YEARS, apply_credit, limitation


def _one(x: float) -> np.ndarray:
    return np.array([x])


def test_the_limitation_is_the_foreign_share_of_us_tax() -> None:
    """§ 904(a): US tax times foreign-source income over worldwide income.

    Not "the foreign tax paid" — the credit relieves double taxation on foreign income
    and may never shelter US tax on US-source income.
    """
    capped = limitation(_one(20_000.0), foreign_source_income=_one(75.0), total_income=_one(100.0))

    assert capped == pytest.approx(15_000.0)


def test_all_foreign_income_makes_the_limitation_the_whole_us_tax() -> None:
    """The common expat case: everything is foreign-source, so nothing is held back."""
    capped = limitation(_one(20_000.0), foreign_source_income=_one(100.0), total_income=_one(100.0))

    assert capped == pytest.approx(20_000.0)


def test_no_income_at_all_is_not_a_division_by_zero() -> None:
    """A year with no income has no limitation, and must not produce a nan."""
    capped = limitation(_one(0.0), foreign_source_income=_one(0.0), total_income=_one(0.0))

    assert capped == pytest.approx(0.0)


def test_a_high_tax_country_wipes_out_the_us_charge_and_banks_the_rest() -> None:
    """The Netherlands taxes harder than the US on the same income.

    Which is the whole reason a US person in NL usually owes nothing and still has to
    file — and the excess is not wasted, it banks.
    """
    charged, carried = apply_credit(
        _one(10_000.0),
        foreign_tax_paid=_one(14_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=(),
    )

    assert charged == pytest.approx(0.0)
    assert sum(float(v[0]) for v in carried) == pytest.approx(4_000.0)


def test_a_credit_never_exceeds_the_limitation() -> None:
    """Half the income is US-source, so half the US tax stands however much NL charged."""
    charged, _ = apply_credit(
        _one(10_000.0),
        foreign_tax_paid=_one(50_000.0),
        foreign_source_income=_one(50.0),
        total_income=_one(100.0),
        carryforward=(),
    )

    assert charged == pytest.approx(5_000.0)


def test_a_banked_credit_is_consumed_in_a_later_year() -> None:
    """The point of the carryforward: a high-tax year pays for a low-tax one."""
    _, carried = apply_credit(
        _one(1_000.0),
        foreign_tax_paid=_one(9_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=(),
    )

    charged, left = apply_credit(
        _one(5_000.0),
        foreign_tax_paid=_one(0.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=carried,
    )

    assert charged == pytest.approx(0.0)
    assert sum(float(v[0]) for v in left) == pytest.approx(3_000.0)


def test_the_current_years_foreign_tax_is_used_before_the_bank() -> None:
    """§ 904(c) order. It matters because only the bank expires."""
    _, banked = apply_credit(
        _one(1_000.0),
        foreign_tax_paid=_one(5_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=(),
    )

    _, after = apply_credit(
        _one(3_000.0),
        foreign_tax_paid=_one(3_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=banked,
    )

    assert sum(float(v[0]) for v in after) == pytest.approx(4_000.0), (
        "this year's own foreign tax should have covered the whole charge, "
        "leaving the bank untouched"
    )


def test_a_banked_credit_expires_after_ten_years() -> None:
    """§ 904(c) gives ten years forward. An eleventh year finds nothing left."""
    _, carried = apply_credit(
        _one(0.0),
        foreign_tax_paid=_one(8_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=(),
    )

    # Ten lean years: no US tax, so no limitation, so nothing is consumed — only aged.
    for _ in range(CARRYFORWARD_YEARS):
        _, carried = apply_credit(
            _one(0.0),
            foreign_tax_paid=_one(0.0),
            foreign_source_income=_one(100.0),
            total_income=_one(100.0),
            carryforward=carried,
        )

    charged, _ = apply_credit(
        _one(6_000.0),
        foreign_tax_paid=_one(0.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=carried,
    )

    assert charged == pytest.approx(6_000.0), "the banked credit should have expired"


def test_it_survives_the_ninth_year() -> None:
    """The off-by-one guard: nine idle years must leave the credit usable."""
    _, carried = apply_credit(
        _one(0.0),
        foreign_tax_paid=_one(8_000.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=(),
    )
    for _ in range(CARRYFORWARD_YEARS - 1):
        _, carried = apply_credit(
            _one(0.0),
            foreign_tax_paid=_one(0.0),
            foreign_source_income=_one(100.0),
            total_income=_one(100.0),
            carryforward=carried,
        )

    charged, _ = apply_credit(
        _one(6_000.0),
        foreign_tax_paid=_one(0.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=carried,
    )

    assert charged == pytest.approx(0.0)


def test_the_oldest_vintage_is_spent_first() -> None:
    """Otherwise a bank that is never fully drawn down would expire from the wrong end."""
    carried: tuple[np.ndarray, ...] = ()
    for _ in range(2):
        _, carried = apply_credit(
            _one(0.0),
            foreign_tax_paid=_one(5_000.0),
            foreign_source_income=_one(100.0),
            total_income=_one(100.0),
            carryforward=carried,
        )

    _, left = apply_credit(
        _one(5_000.0),
        foreign_tax_paid=_one(0.0),
        foreign_source_income=_one(100.0),
        total_income=_one(100.0),
        carryforward=carried,
    )

    assert float(left[0][0]) == pytest.approx(0.0), "the older vintage should be empty"
    assert sum(float(v[0]) for v in left) == pytest.approx(5_000.0), "the newer one intact"


def test_the_credit_is_vectorised_over_runs() -> None:
    """Invariant #6: each run carries its own bank."""
    charged, carried = apply_credit(
        np.array([10_000.0, 10_000.0, 10_000.0]),
        foreign_tax_paid=np.array([0.0, 6_000.0, 20_000.0]),
        foreign_source_income=np.full(3, 100.0),
        total_income=np.full(3, 100.0),
        carryforward=(),
    )

    assert charged == pytest.approx([10_000.0, 4_000.0, 0.0])
    assert carried[-1] == pytest.approx([0.0, 0.0, 10_000.0])
