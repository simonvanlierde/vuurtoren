"""One-off taxes at purchase and gifting."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vuurtoren.tax.nl.config import NLTaxConfig

_CENTS = Decimal("0.01")


def _round(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _birthday(birth_date: date, age: int) -> date:
    """The day `birth_date` turns `age`; a 29 February birthday falls on 28 February."""
    year = birth_date.year + age
    try:
        return birth_date.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def transfer_tax(
    price: Decimal,
    *,
    buyer_age: int,
    own_occupancy: bool,
    starter_exemption_used: bool,
    cfg: NLTaxConfig,
) -> tuple[Decimal, bool]:
    """Overdrachtsbelasting: 0% starter, 2% own home, 8% otherwise.

    Returns `(duty, exemption_applied)`. `exemption_applied` is whether the starter
    exemption actually zeroed this purchase — the caller uses it to decide whether the
    single-use exemption is now consumed, without re-deriving the qualification rule.

    `buyer_age` is the buyer's age at the notary date, which the caller computes from
    the milestone date — not from today.
    """
    if not own_occupancy:
        return _round(price * cfg.transfer_tax_general_rate), False

    qualifies = (
        not starter_exemption_used
        and buyer_age < cfg.starter_exemption_max_age
        and price <= cfg.starter_exemption_value_cap
    )
    if qualifies:
        return Decimal("0.00"), True
    return _round(price * cfg.transfer_tax_own_home_rate), False


def gift_tax_free_amount(
    amount: Decimal,
    *,
    recipient_birth_date: date,
    gift_date: date,
    onetime_used: bool,
    cfg: NLTaxConfig,
) -> Decimal:
    """The tax-free portion of a parental gift.

    The one-time increased exemption and the annual exemption are mutually exclusive in
    the same year, so this returns whichever applies — never their sum. The one-time
    exemption runs from the 18th birthday up to and including the 40th: the Belastingdienst
    allows a gift on the 40th birthday itself and none after it.
    """
    eligible = not onetime_used and _birthday(
        recipient_birth_date, cfg.gift_exemption_min_age
    ) <= gift_date <= _birthday(recipient_birth_date, cfg.gift_exemption_max_age)
    cap = cfg.gift_exemption_onetime if eligible else cfg.gift_exemption_annual
    return _round(min(amount, cap))
