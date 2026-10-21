"""§ 1296 mark-to-market on a passive foreign investment company.

Every non-US fund a US person can buy in Europe is a PFIC — a UCITS ETF included — and
the default § 1291 excess-distribution regime is punitive enough that nobody sensible
lives under it. The app models the mark-to-market election and *refuses* the unelected
case, because the honest answer there is that the position should not be held rather than
a number. `check_no_unelected_pfic` is that refusal, and its message is the feature.

**The yearly rise is ordinary income, not a capital gain.** § 1296(a)(1) includes the
excess of value over basis in gross income at ordinary rates, so this module returns an
*income inclusion* for the caller to add to the ordinary base rather than a tax of its
own — no second ladder, no rate of its own to keep verified. A fall is deductible under
§ 1296(a)(2), but only against unreversed inclusions: what this holding has already been
taxed on and not yet given back.

**State lives in the caller, not here.** These functions take the pool and return the new
one, so nothing here remembers a year. The overlay passes the pool on in its `USCarry`,
beside the credit carryforward — the two are the only cross-year state in this design.

**The pool is per overlay *treatment*, and § 1296 is per *security*.** The overlay is
handed treatment-keyed maps rather than accounts (`PersonSlice`), so one pool covers all
of a person's mark-to-market holdings together. That lets a loss on one PFIC be deducted
against inclusions banked on another, which the statute does not allow — so it permits
more deduction than the law and therefore **understates** US tax for a household holding
several PFICs whose returns diverge. It is exact for the single-PFIC case, which is the
common one. Splitting it needs per-account overlay state, which is the same change as
giving the overlay accounts instead of maps.
"""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vuurtoren.domain import Account, Person

MTM = "us.pfic_mtm"
"""A PFIC under a § 1296 mark-to-market election."""

UNELECTED = "us.pfic_none"
"""A PFIC with no election — the refused case."""


def mark_to_market_inclusion(
    value_growth: np.ndarray, *, unreversed_inclusions: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """One year of § 1296, per run: `(inclusion, unreversed_inclusions_after)`.

    `inclusion` is positive for a rise and negative for a deductible fall, and goes into
    the person's ordinary income. `value_growth` is the year's change in value — the
    engine already computes it for Austria's non-reporting funds, so this reuses that
    base rather than asking for a new one.

    The returned pool is `prior + inclusion`, which is § 1296(d)'s definition: inclusions
    so far, less deductions so far. It can never go negative, because the deduction is
    capped by the pool it draws on.
    """
    gain = np.maximum(0.0, value_growth)
    deductible = np.minimum(np.maximum(0.0, -value_growth), unreversed_inclusions)
    inclusion = gain - deductible
    return inclusion, unreversed_inclusions + inclusion


def sale_gain_after_step_up(
    realized_gain: np.ndarray, *, unreversed_inclusions: np.ndarray
) -> np.ndarray:
    """The part of a sale's gain mark-to-market has not already taxed.

    § 1296(b) raises basis by every inclusion and lowers it by every deduction, which is
    exactly the unreversed pool — so the overlay carries its own step-up over whatever
    cost basis the engine tracks for the residence regime. Without it a holding marked up
    for a decade would be taxed in full a second time on the day it is sold.

    Floored at zero: a pool larger than the gain means the whole gain was taxed already,
    not that a refund is due. Gain on a § 1296 disposition is ordinary (§ 1296(c)(1)(A)),
    so the caller must not route this through the preferential rates.
    """
    return np.maximum(0.0, realized_gain - unreversed_inclusions)


def check_no_unelected_pfic(accounts: Sequence[Account], *, person: Person) -> None:
    """Raise if this person holds a PFIC with no mark-to-market election.

    Covers accounts they own outright and accounts the household holds jointly: what
    share of a joint holding falls inside the US net follows from filing status, and no
    share of an unelected PFIC is a share worth holding.
    """
    for account in accounts:
        if account.overlay_treatment != UNELECTED:
            continue
        if account.owner_person_id not in (person.id, None):
            continue
        msg = (
            f"{person.name} is a US person and holds {account.name!r}, classified "
            f"{UNELECTED!r}: a passive foreign investment company with no election. "
            f"Vuurtoren does not model the § 1291 excess-distribution regime, because "
            f"the honest answer is that the holding should not be held rather than a "
            f"number. Two ways out: elect mark-to-market on it ({MTM!r}), or hold a "
            f"non-PFIC asset such as a US-domiciled fund ('us.non_pfic')."
        )
        raise ValueError(msg)
