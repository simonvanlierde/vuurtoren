"""Austrian Einkommensteuer on wage income, at parity with the Dutch `box1.gross_to_net`.

Seven bands rather than the Netherlands' three, so the schedule is expressed as a list of
(upper bound, rate) pairs built from the config rather than unrolled by hand. That also
means the shape survives Austria's annual `kalte Progression` indexation, which moves
every threshold but the top one each year.

Not reachable through `TaxRegime`: no protocol method taxes wage income, in either
country. This is a helper on the same footing as its Dutch counterpart.

Social insurance is deducted before the tariff, because contributions are compulsory and
reduce the income tax base (§ 16 EStG). That ordering is the whole reason a naive
"apply the bracket table to gross" overstates Austrian tax badly.

The other reason a naive calculation is wrong is the *Jahressechstel*: Austrian pay is
usually quoted as 14 payments a year, and the two extra ones are taxed at a flat 6%
rather than at the marginal rate.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vuurtoren.tax.at.config import ATTaxConfig

_ZERO = Decimal(0)
_CENTS = Decimal("0.01")


def _round(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _bands(cfg: ATTaxConfig) -> list[tuple[Decimal, Decimal]]:
    """The tariff as (upper bound, marginal rate), lowest band first.

    The final band has no upper bound; `None` would force every caller to special-case
    it, so it carries a bound no income reaches instead.
    """
    return [
        (cfg.income_bracket_1_to, cfg.income_rate_1),
        (cfg.income_bracket_2_to, cfg.income_rate_2),
        (cfg.income_bracket_3_to, cfg.income_rate_3),
        (cfg.income_bracket_4_to, cfg.income_rate_4),
        (cfg.income_bracket_5_to, cfg.income_rate_5),
        (cfg.income_bracket_6_to, cfg.income_rate_6),
        (Decimal("1e12"), cfg.income_rate_7),
    ]


def social_insurance(gross_annual: Decimal, *, cfg: ATTaxConfig) -> Decimal:
    """Employee social insurance contributions, capped at the Hoechstbeitragsgrundlage.

    A single blended employee rate rather than the five separate branches: the split
    between health, pension, unemployment and the rest changes nothing about net income,
    and carrying five figures would mean re-verifying five every January.

    Not modelled: the tapered unemployment contribution on low incomes, and Vienna's
    higher Wohnbaufoerderungsbeitrag. Both move the rate by well under a point.
    """
    if gross_annual <= _ZERO:
        return _ZERO
    base = min(gross_annual, cfg.social_insurance_ceiling)
    return _round(base * cfg.social_insurance_employee_rate)


def income_tax(taxable_annual: Decimal, *, cfg: ATTaxConfig) -> Decimal:
    """Einkommensteuer on an already-SV-reduced base, before Absetzbetraege."""
    if taxable_annual <= _ZERO:
        return _ZERO
    tax = _ZERO
    lower = _ZERO
    for upper, rate in _bands(cfg):
        if taxable_annual <= lower:
            break
        tax += (min(taxable_annual, upper) - lower) * rate
        lower = upper
    return tax


def sonderzahlung_tax(sonstige: Decimal, *, cfg: ATTaxConfig) -> Decimal:
    """Tax on the 13th and 14th salary, § 67 EStG.

    Exempt entirely below the Freigrenze; otherwise a flat 6% on what is left after the
    Freibetrag. This is why an Austrian salary nets more than the headline tariff
    suggests, and ignoring it understated net pay by over a thousand euros at an
    ordinary wage.
    """
    if sonstige <= cfg.sonderzahlung_exempt_below:
        return _ZERO
    return max(_ZERO, sonstige - cfg.sonderzahlung_allowance) * cfg.sonderzahlung_rate


def gross_to_net(
    gross_annual: Decimal, *, cfg: ATTaxConfig, sonderzahlungen: bool = True
) -> Decimal:
    """Net annual wage income after social insurance and Einkommensteuer.

    Austrian pay is normally quoted as 14 payments a year, and the two extra ones are
    taxed at a flat 6% rather than at the marginal rate. `sonderzahlungen=True` splits
    `gross_annual` on that basis; pass False for a salary genuinely paid in 12 equal
    parts, where the whole amount runs through the tariff.

    Deducts the Verkehrsabsetzbetrag, which every employee receives; the income-dependent
    supplements and the Familienbonus are not modelled, so this understates net income
    for those who qualify. Absetzbetraege reduce the tax to zero and no further — the
    negative-tax (SV-Rueckerstattung) case is not modelled either.
    """
    if gross_annual <= _ZERO:
        return _ZERO
    sv = social_insurance(gross_annual, cfg=cfg)
    if not sonderzahlungen:
        tax = max(_ZERO, income_tax(gross_annual - sv, cfg=cfg) - cfg.employee_credit)
        return _round(gross_annual - sv - tax)

    # SV is charged on the whole year's pay, so it is split in the same proportion as the
    # pay itself before each part meets its own tariff.
    sonstige = gross_annual * cfg.sonderzahlung_share
    regular = gross_annual - sonstige
    sv_sonstige = sv * cfg.sonderzahlung_share
    sv_regular = sv - sv_sonstige

    tax = max(_ZERO, income_tax(regular - sv_regular, cfg=cfg) - cfg.employee_credit)
    tax += sonderzahlung_tax(sonstige - sv_sonstige, cfg=cfg)
    return _round(gross_annual - sv - tax)
