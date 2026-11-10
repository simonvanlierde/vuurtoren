"""Box 1 — income tax on wages and lijfrente uitkeringen; the owner-occupied home.

The income schedule is the real one: three brackets, the first without the AOW premium
from AOW age, and the algemene heffingskorting, arbeidskorting and ouderenkorting with
their income-dependent phase-outs. What it leaves out, and which way that bends the
answer, is in `box1_tax_array`.

Annuity/amortisation maths is country-neutral and lives in `vuurtoren.mortgage`.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vuurtoren.tax.nl.config import NLTaxConfig

_CENTS = Decimal("0.01")
_ZERO = Decimal(0)

# Wet Hillen phase-out baseline year. cfg.year is the query year (defaults_for stamps it
# per call), not a fixed anchor, so the baseline the phase-out counts from lives here
# rather than in cfg.
_HILLEN_BASE_YEAR = 2026


def _round(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


def gross_to_net(gross_annual: Decimal, *, cfg: NLTaxConfig) -> Decimal:
    """Net annual wage income after Box 1 tax, below AOW age.

    `box1_tax_array` on the whole wage as labour income. Decimal in and out; the schedule
    runs in float64 like every other engine array and is rounded once, to the cent.
    """
    if gross_annual <= _ZERO:
        return _ZERO
    tax = box1_tax_array(
        np.array([float(gross_annual)]),
        labour_income=np.array([float(gross_annual)]),
        aow_share=0.0,
        cfg=cfg,
    )
    return _round(gross_annual - Decimal(repr(float(tax[0]))))


def _brackets(income: np.ndarray, rate_1: float, cfg: NLTaxConfig) -> np.ndarray:
    """The three-bracket tax on `income` before any korting."""
    b1, b2 = float(cfg.box1_bracket_1_to), float(cfg.box1_bracket_2_to)
    return (
        np.minimum(income, b1) * rate_1
        + np.clip(income - b1, 0.0, b2 - b1) * float(cfg.box1_rate_2)
        + np.maximum(income - b2, 0.0) * float(cfg.box1_rate_3)
    )


def _phased(maximum: Decimal, income: np.ndarray, start: Decimal, rate: Decimal) -> np.ndarray:
    """A korting at `maximum`, reduced by `rate` per euro of income above `start`."""
    return np.maximum(0.0, float(maximum) - float(rate) * np.maximum(0.0, income - float(start)))


def _labour_credit(labour: np.ndarray, cfg: NLTaxConfig) -> np.ndarray:
    """The arbeidskorting, segment by segment as the Belastingdienst table states it."""
    k1, k2, k3 = (
        float(cfg.labour_credit_knot_1),
        float(cfg.labour_credit_knot_2),
        float(cfg.labour_credit_knot_3),
    )
    labour = np.maximum(labour, 0.0)
    return np.select(
        [labour <= k1, labour <= k2, labour <= k3],
        [
            float(cfg.labour_credit_rate_1) * labour,
            float(cfg.labour_credit_base_2) + float(cfg.labour_credit_rate_2) * (labour - k1),
            float(cfg.labour_credit_base_3) + float(cfg.labour_credit_rate_3) * (labour - k2),
        ],
        default=_phased(
            cfg.labour_credit_max, labour, cfg.labour_credit_knot_3, cfg.labour_credit_phaseout_rate
        ),
    )


def box1_tax_array(
    income: np.ndarray, *, labour_income: np.ndarray, aow_share: float, cfg: NLTaxConfig
) -> np.ndarray:
    """Box 1 tax on a year's `income`, after the heffingskortingen, over (n_runs,) arrays.

    Below AOW age: the three brackets, minus the algemene heffingskorting and the
    arbeidskorting on `labour_income`, each phased out as the tables say. From AOW age:
    the first bracket without the AOW premium, minus the AOW-age algemene
    heffingskorting and the ouderenkorting; no arbeidskorting, because an AOW-age
    person's income is taken to be AOW and pension. `aow_share` is the part of the year
    at AOW age (`aow.aow_year_share`), and the two schedules are blended by it. For the
    first-bracket rate that blend is exactly the Belastingdienst's month-by-month table;
    for the kortingen in that one year it is an approximation of what the
    Belastingdienst computes per person. The kortingen bring the tax to zero, never
    below: no refund, and no uitbetaling of the algemene heffingskorting to a partner.

    Not modelled, and which way each bends the answer:
    - the phase-outs run on Box 1 income, while the law reads the verzamelinkomen, so
      Box 3 income never phases a korting out (understates);
    - the alleenstaande-ouderenkorting and the other kortingen are absent (overstates);
    - the bracket bound for people born before 1946 (41,123 in 2026) is not used; the
      projection starts in 2026, when they are 80 or older (overstates for them).
    """
    income = np.maximum(income, 0.0)
    below = _below_aow(income, labour_income, cfg)
    above = _at_aow(income, cfg)
    return (1.0 - aow_share) * np.maximum(below, 0.0) + aow_share * np.maximum(above, 0.0)


def _below_aow(income: np.ndarray, labour: np.ndarray, cfg: NLTaxConfig) -> np.ndarray:
    """The below-AOW-age tax after kortingen, before the floor at zero."""
    return (
        _brackets(income, float(cfg.box1_rate_1), cfg)
        - _phased(
            cfg.general_credit_max,
            income,
            cfg.general_credit_phaseout_from,
            cfg.general_credit_phaseout_rate,
        )
        - _labour_credit(labour, cfg)
    )


def _at_aow(income: np.ndarray, cfg: NLTaxConfig) -> np.ndarray:
    """The AOW-age tax after kortingen, before the floor at zero."""
    return (
        _brackets(income, float(cfg.box1_rate_1 - cfg.aow_premium_rate), cfg)
        - _phased(
            cfg.general_credit_max_aow,
            income,
            cfg.general_credit_phaseout_from,
            cfg.general_credit_phaseout_rate_aow,
        )
        - _phased(
            cfg.elderly_credit_max,
            income,
            cfg.elderly_credit_phaseout_from,
            cfg.elderly_credit_phaseout_rate,
        )
    )


def _phase_end(start: Decimal, maximum: Decimal, rate: Decimal) -> float:
    """Where a korting phased out from `start` at `rate` reaches zero."""
    return float(start + maximum / rate) if rate > 0 else float(start)


# Far past every bound, so the last linear piece of the schedule is covered.
_FAR = 1e10


def gross_from_net_array(net: np.ndarray, *, aow_share: float, cfg: NLTaxConfig) -> np.ndarray:
    """The gross income whose net after `box1_tax_array` is `net`, all of it labour income.

    The inverse of `gross_to_net`. Net is piecewise linear in gross, bending only at the
    bracket bounds, the korting knots and the two points where the tax first rises above
    zero, so evaluating it at those points and interpolating back is exact to well under
    a cent. It relies on the tax rising with income, which the shipped figures do
    everywhere: the steepest korting build-up (31%) is below the lowest bracket rate.
    """
    knots = np.array(
        [
            0.0,
            float(cfg.box1_bracket_1_to),
            float(cfg.box1_bracket_2_to),
            float(cfg.general_credit_phaseout_from),
            _phase_end(
                cfg.general_credit_phaseout_from,
                cfg.general_credit_max,
                cfg.general_credit_phaseout_rate,
            ),
            _phase_end(
                cfg.general_credit_phaseout_from,
                cfg.general_credit_max_aow,
                cfg.general_credit_phaseout_rate_aow,
            ),
            float(cfg.labour_credit_knot_1),
            float(cfg.labour_credit_knot_2),
            float(cfg.labour_credit_knot_3),
            _phase_end(
                cfg.labour_credit_knot_3, cfg.labour_credit_max, cfg.labour_credit_phaseout_rate
            ),
            float(cfg.elderly_credit_phaseout_from),
            _phase_end(
                cfg.elderly_credit_phaseout_from,
                cfg.elderly_credit_max,
                cfg.elderly_credit_phaseout_rate,
            ),
            _FAR,
        ]
    )
    # The arbeidskorting table's rounded amounts jump by a few cents at its knots, so
    # each knot is also taken a tenth of a cent to its right.
    knots = np.union1d(knots, knots + 0.001)
    # Where each schedule's tax crosses zero: rising and linear between knots, so one
    # interpolation finds it.
    zero_below = np.interp(0.0, _below_aow(knots, knots, cfg), knots)
    zero_at = np.interp(0.0, _at_aow(knots, cfg), knots)
    knots = np.sort(np.append(knots, [zero_below, zero_at]))
    nets = knots - box1_tax_array(knots, labour_income=knots, aow_share=aow_share, cfg=cfg)
    return np.interp(np.maximum(net, 0.0), nets, knots)


def net_housing_tax_effect_array(
    interest_paid_year: np.ndarray, woz: np.ndarray, *, year: int, cfg: NLTaxConfig
) -> np.ndarray:
    """Signed annual Box 1 effect of owning the home, over (n_runs,) arrays.

    Positive is a net deduction (interest exceeds the eigenwoningforfait). Negative is
    net tax owed: once the forfait exceeds interest paid, the excess is taxable income,
    reduced by the phasing-out Wet Hillen relief (aftrek wegens geen of geringe
    eigenwoningschuld). The forfait has two tiers; the upper one is the villatax. Runs
    without a home (woz <= 0) return 0.
    """
    ewf = np.round(
        np.minimum(np.maximum(woz, 0.0), float(cfg.ewf_threshold)) * float(cfg.ewf_rate)
        + np.maximum(0.0, woz - float(cfg.ewf_threshold)) * float(cfg.ewf_high_rate),
        2,
    )
    deduction = np.round((interest_paid_year - ewf) * float(cfg.hra_max_rate), 2)
    hillen = max(
        0.0,
        float(cfg.hillen_rate) - (year - _HILLEN_BASE_YEAR) * float(cfg.hillen_phaseout_per_year),
    )
    owed = -np.round((ewf - interest_paid_year) * (1.0 - hillen) * float(cfg.hra_max_rate), 2)
    return np.where(woz > 0.0, np.where(interest_paid_year >= ewf, deduction, owed), 0.0)


def pension_withdrawal_tax_array(
    amount: np.ndarray, *, other_income: np.ndarray, aow_share: float, cfg: NLTaxConfig
) -> np.ndarray:
    """Box 1 tax on taking `amount` out of a lijfrente, stacked on `other_income`.

    A uitkering is Box 1 income on top of whatever else the person has that year, so its
    tax is the difference it makes: tax(other + amount) - tax(other), through the real
    brackets and kortingen (`box1_tax_array`). `other_income` is gross and counts as
    labour income below AOW age; the arbeidskorting stays on it, since a uitkering is not
    work. The difference is rounded to the cent. A negative amount is a deposit, not a
    withdrawal, and is never taxed here.
    """

    def tax(income: np.ndarray) -> np.ndarray:
        return box1_tax_array(income, labour_income=other_income, aow_share=aow_share, cfg=cfg)

    return np.round(tax(other_income + np.maximum(amount, 0.0)) - tax(other_income), 2)
