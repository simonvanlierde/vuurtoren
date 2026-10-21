"""The foreign tax credit — § 901 and the § 904 limitation, with its carryforward.

This is what makes a US person resident in a high-tax country usually owe the United
States nothing while still having to file. The credit is not "the foreign tax paid": it
is capped at the share of US tax that falls on *foreign-source* income, because the
credit relieves double taxation and may never shelter US tax on US-source income. For the
retained US brokerage account that cap would bite hard, which is exactly what the
treaty's re-sourcing article is for — phase 4's job, not this module's.

**Where the state lives, decided here for the whole design.** § 904(c) carries unused
credit forward ten years, which is per-run state spanning years — the only such state in
this design, now that Task 6's PFIC pool takes the same shape. Three homes were possible
and two are wrong:

- *`PersonSlice`* would make the engine carry it, and `engine.py` may not know what a
  foreign tax credit is (invariant #1).
- *`HouseholdTax`* is the country-neutral composite; a US-shaped bank of vintages there
  would leak citizenship rules into the layer whose whole job is not to have any.
- *The overlay* is right: `USCitizenshipOverlay.annual_tax` takes the bank in its
  `USCarry` and returns the new one. `HouseholdTax` stores that carry without reading it,
  so the composite still knows nothing US-shaped.

So this module stays a pure function of (year, bank) → (charge, new bank), exactly like
`pfic.py`. Nothing here remembers a year.

**Carryback is not modelled.** § 904(c) also allows one year back, which means reopening
a year a forward projection has already reported. Unused credit therefore waits for a
later year or expires, where a carryback would have refunded tax already charged — so
this **overstates** cumulative US tax, never understates it.

**One basket, the passive one.** § 904(d) splits the limitation between a passive and a
general basket, and running both would need every income item classified twice. This
household's foreign income is investment income and Dutch wage income; wage income is
general-basket, but it is also the income the FEIE excludes first (`income.py`), so what
reaches the credit is overwhelmingly passive. Where a large unexcluded salary remains,
one basket is more generous than two and understates US tax — the one place in this
module that errs that way.
"""

import numpy as np

CARRYFORWARD_YEARS = 10
"""§ 904(c): unused credit is usable for ten years after the year it arose."""


def limitation(
    us_tax: np.ndarray, *, foreign_source_income: np.ndarray, total_income: np.ndarray
) -> np.ndarray:
    """§ 904(a): the most credit this year can absorb, per run.

    US tax scaled by the foreign-source share of income. A year with no income at all
    divides zero by zero, which is a real case (a retiree living off capital already
    taxed) and must be a limitation of zero rather than a nan quietly poisoning the rest
    of the projection.
    """
    total = np.asarray(total_income, dtype=float)
    share = np.divide(
        np.maximum(0.0, foreign_source_income),
        total,
        out=np.zeros_like(total),
        where=total > 0,
    )
    return np.maximum(0.0, us_tax) * np.clip(share, 0.0, 1.0)


def apply_credit(
    us_tax: np.ndarray,
    *,
    foreign_tax_paid: np.ndarray,
    foreign_source_income: np.ndarray,
    total_income: np.ndarray,
    carryforward: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """One year of the credit: `(US tax after credit, the bank for next year)`.

    `carryforward` is oldest vintage first, at most `CARRYFORWARD_YEARS` of them. Each
    entry is a `(n_runs,)` array, so every Monte Carlo run banks and spends its own
    credit — a run where the market fell has a different bank from one where it rose.

    § 904(c)'s order is followed: this year's own foreign tax is credited first, and only
    the limitation left over draws on the bank, oldest vintage first. Both halves of that
    matter — crediting the bank first would let credit that never expires be spent while
    credit that does sits and dies.
    """
    paid = np.maximum(0.0, foreign_tax_paid)
    remaining = limitation(
        us_tax, foreign_source_income=foreign_source_income, total_income=total_income
    )

    from_this_year = np.minimum(paid, remaining)
    remaining = remaining - from_this_year
    credited = from_this_year

    spent: list[np.ndarray] = []
    for vintage in carryforward:  # oldest first
        drawn = np.minimum(vintage, remaining)
        remaining = remaining - drawn
        credited = credited + drawn
        spent.append(vintage - drawn)

    # This year's unused foreign tax joins the bank, and anything that has aged past the
    # tenth year falls off the front. The new vintage is appended even when it is zero, so
    # one call is one year of ageing whether or not there was any excess to bank.
    banked = (*spent, paid - from_this_year)
    return us_tax - credited, banked[-CARRYFORWARD_YEARS:]
