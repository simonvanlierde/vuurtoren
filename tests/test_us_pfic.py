"""§ 1296 mark-to-market: the yearly inclusion, the loss cap, and the loud failure."""

import numpy as np
import pytest

from vuurtoren.domain import Account, AccountKind, Person
from vuurtoren.tax.us.federal.pfic import (
    MTM,
    UNELECTED,
    check_no_unelected_pfic,
    mark_to_market_inclusion,
    sale_gain_after_step_up,
)


def _one(x: float) -> np.ndarray:
    return np.array([x])


def _account(*, overlay: str | None, owner: int | None = 1, name: str = "iShares Core") -> Account:
    return Account(
        id=1,
        household_id=1,
        name=name,
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        overlay_treatment=overlay,
        owner_person_id=owner,
    )


def _us_person() -> Person:
    return Person(id=1, household_id=1, name="Sam", us_person=True)


def test_a_years_rise_is_included_in_full() -> None:
    """§ 1296(a)(1): the excess of value over basis is ordinary income, every year."""
    inclusion, pool = mark_to_market_inclusion(_one(8_000.0), unreversed_inclusions=_one(0.0))

    assert inclusion == pytest.approx(8_000.0)
    assert pool == pytest.approx(8_000.0)


def test_a_loss_is_deductible_only_up_to_prior_inclusions() -> None:
    """§ 1296(a)(2): the deduction is capped by unreversed inclusions.

    Without the cap a falling PFIC would generate an unlimited ordinary deduction against
    the rest of the person's US income, which is the opposite of what the regime is for.
    """
    inclusion, pool = mark_to_market_inclusion(_one(-5_000.0), unreversed_inclusions=_one(3_000.0))

    assert inclusion == pytest.approx(-3_000.0)
    assert pool == pytest.approx(0.0)


def test_a_loss_with_no_prior_inclusions_deducts_nothing() -> None:
    """A PFIC bought and immediately fallen gives no deduction at all."""
    inclusion, pool = mark_to_market_inclusion(_one(-9_000.0), unreversed_inclusions=_one(0.0))

    assert inclusion == pytest.approx(0.0)
    assert pool == pytest.approx(0.0)


def test_the_pool_tracks_across_years() -> None:
    """Gain, loss, gain — the pool is what makes the middle year's deduction legal."""
    pool = _one(0.0)
    inclusions = []
    for growth in (10_000.0, -4_000.0, 6_000.0):
        inclusion, pool = mark_to_market_inclusion(_one(growth), unreversed_inclusions=pool)
        inclusions.append(float(inclusion[0]))

    assert inclusions == pytest.approx([10_000.0, -4_000.0, 6_000.0])
    assert pool == pytest.approx(12_000.0)


def test_a_sale_is_not_taxed_on_what_mark_to_market_already_taxed() -> None:
    """The overlay's own step-up: § 1296(b) raises basis by every inclusion.

    Without it a holding marked up for ten years would be taxed a second time in full on
    the day it is sold.
    """
    after = sale_gain_after_step_up(_one(30_000.0), unreversed_inclusions=_one(12_000.0))

    assert after == pytest.approx(18_000.0)


def test_the_step_up_cannot_turn_a_sale_into_a_refund() -> None:
    """A pool larger than the realized gain leaves zero, not a negative gain."""
    after = sale_gain_after_step_up(_one(5_000.0), unreversed_inclusions=_one(12_000.0))

    assert after == pytest.approx(0.0)


def test_an_unelected_pfic_fails_loudly_naming_both_ways_out() -> None:
    """The message is the feature: the § 1291 regime is not modelled on purpose."""
    with pytest.raises(ValueError, match="iShares Core") as caught:
        check_no_unelected_pfic([_account(overlay=UNELECTED)], person=_us_person())

    message = str(caught.value)
    assert MTM in message, "the message must name the mark-to-market election"
    assert "us.non_pfic" in message, "the message must name the other way out"
    assert "Sam" in message


def test_a_jointly_held_unelected_pfic_also_fails() -> None:
    """A joint account is not outside the US net.

    Filing status decides the share, and even the smallest share is a holding the person
    should not have.
    """
    with pytest.raises(ValueError, match="Joint fund"):
        check_no_unelected_pfic(
            [_account(overlay=UNELECTED, owner=None, name="Joint fund")], person=_us_person()
        )


def test_an_unelected_pfic_owned_by_someone_else_is_not_this_persons_problem() -> None:
    """The non-US spouse's own PFIC is theirs to hold."""
    check_no_unelected_pfic([_account(overlay=UNELECTED, owner=2)], person=_us_person())


def test_elected_and_non_pfic_holdings_pass() -> None:
    """An election, a US-domiciled fund, and an unclassified account are all fine."""
    accounts = [
        _account(overlay=MTM),
        _account(overlay="us.non_pfic"),
        _account(overlay=None),
    ]

    check_no_unelected_pfic(accounts, person=_us_person())


def test_the_inclusion_is_vectorised_over_runs() -> None:
    """Invariant #6 — one PFIC, many runs, each with its own pool."""
    growth = np.array([10_000.0, -2_000.0, -8_000.0])
    pools = np.array([0.0, 5_000.0, 3_000.0])

    inclusion, after = mark_to_market_inclusion(growth, unreversed_inclusions=pools)

    assert inclusion == pytest.approx([10_000.0, -2_000.0, -3_000.0])
    assert after == pytest.approx([10_000.0, 3_000.0, 0.0])
