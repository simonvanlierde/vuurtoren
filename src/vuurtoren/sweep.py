"""Holding the cash account inside its buffer.

Country-neutral and pure, like `mortgage.py`: arrays in, arrays out, no tax logic and
no knowledge of what any `tax_treatment` string means. The engine decides how large the
buffer is and which flows are taxable; this module only moves the money.
"""

from typing import TYPE_CHECKING, Literal

import numpy as np

from vuurtoren.domain import Account, AccountKind

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

SweepOrder = Literal["pro_rata", "safest_first", "riskiest_first"]
"""How a shortfall is raised. Selling only — buying is always pro-rata.

A withdrawal order is a real, named strategy and it governs roughly thirty years of
decumulation; a deposit order is not, and pro-rata buying keeps the allocation from
drifting.
"""

_SELLABLE_KINDS = (AccountKind.EQUITY, AccountKind.BOND, AccountKind.PENSION)
"""What the sweep may liquidate. PENSION only once past `liquid_from`, and the caller
charges whatever its regime levies on the withdrawal.

Selling a pension is not symmetric with buying one, which is why `apply_sweep` takes the
buy side as its own list: capital that is taxed coming out must not be a destination for
surplus cash, and a real pension wrapper has contribution limits this module knows
nothing about."""


def sellable_accounts(accounts: Sequence[Account], when: date, order: SweepOrder) -> list[Account]:
    """The accounts the sweep may sell from in month `when`, in sell order.

    `liquid_from` is honoured for every kind, not just pensions: `None` means liquid
    now, matching `_fire_metrics`. Excluding a locked pension avoids the classic bug in
    this class of tool.

    Ties on volatility break on `id`, never on list order — `plan.accounts` arrives from
    an unordered query, the same hazard that makes the engine pick `min(cash_ids)`.
    """
    out = [
        a
        for a in accounts
        if a.kind in _SELLABLE_KINDS and (a.liquid_from is None or when >= a.liquid_from)
    ]
    # Negating the volatility rather than reversing the sorted list: `reverse()` would
    # also flip the id tie-break, so two equal-volatility accounts would drain in
    # opposite order under the two priority modes for no reason anyone intended.
    sign = -1.0 if order == "riskiest_first" else 1.0
    out.sort(key=lambda a: (sign * a.volatility_assumption, a.id))
    return out


def apply_sweep(
    balances: dict[int, np.ndarray],
    cash_id: int,
    sources: list[Account],
    *,
    buy_targets: list[Account] | None = None,
    target: np.ndarray | float,
    deadband: float,
    pro_rata: bool,
) -> dict[int, np.ndarray]:
    """Move money between cash and `sources` so cash sits inside its buffer.

    Mutates `balances`. Returns the signed net flow per source account id, positive
    where money moved *into* that account — the caller needs the signs to keep its
    actual-return base honest, since neither direction is a gain, and to charge whatever
    its regime levies on a withdrawal.

    Selling is best-effort: capped at the positive balances that exist, so cash can
    still close negative when the investments run dry. `sources` must already be in
    sell order (see `sellable_accounts`).

    `buy_targets` is where surplus cash goes, defaulting to `sources`. It is separate
    because the two directions are not symmetric: capital that is taxed on the way out,
    or that sits behind a contribution limit, may be sellable without being a sensible
    destination. The caller decides — this module has no idea which is which.
    """
    if not sources:
        return {}
    if buy_targets is None:
        buy_targets = sources

    ids = [a.id for a in sources]
    buy_ids = [a.id for a in buy_targets]
    cash = balances[cash_id]
    flow = {i: np.zeros_like(cash) for i in {*ids, *buy_ids}}
    threshold = np.asarray(target) * deadband
    # Each pass is skipped in a month when no run needs it, since it would move exactly
    # nothing: most months nobody is below the floor, and many nobody is above the
    # deadband. The tests are the passes' own conditions — `target - cash` is positive
    # exactly when `target > cash`.

    # --- sell to reach the floor ---
    if not np.all(cash >= target):
        positive = {i: np.maximum(balances[i], 0.0) for i in ids}
        total = sum(positive.values(), start=np.zeros_like(cash))
        raised = np.minimum(np.maximum(target - cash, 0.0), total)

        if pro_rata:
            frac = np.divide(raised, total, out=np.zeros_like(raised), where=total > 0)
            for i in ids:
                take = positive[i] * frac
                balances[i] = balances[i] - take
                flow[i] = flow[i] - take
        else:
            remaining = raised.copy()
            for i in ids:
                take = np.minimum(remaining, positive[i])
                balances[i] = balances[i] - take
                flow[i] = flow[i] - take
                remaining = remaining - take

        cash = cash + raised

    # --- invest what sits above the deadband ---
    # Recomputed rather than reused: a run that sold has no surplus and vice versa, but
    # deriving the second pass from the first would couple them for no gain.
    if buy_ids and not np.all(cash <= threshold):
        post = {i: np.maximum(balances[i], 0.0) for i in buy_ids}
        post_total = sum(post.values(), start=np.zeros_like(cash))
        invested = np.maximum(cash - threshold, 0.0)
        give_frac = np.divide(
            invested, post_total, out=np.zeros_like(invested), where=post_total > 0
        )
        for i in buy_ids:
            # Pro-rata of nothing is nothing, so a portfolio that starts at zero would
            # never receive a cent. With no weights to go by, split evenly — the same rule
            # the frontend's allocation scenarios use for an empty side.
            give = np.where(post_total > 0, post[i] * give_frac, invested / len(buy_ids))
            balances[i] = balances[i] + give
            flow[i] = flow[i] + give
        cash = cash - invested

    balances[cash_id] = cash
    return flow
