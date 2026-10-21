"""Country-neutral mortgage amortisation maths. Used by the engine directly."""

from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")
_ZERO = Decimal(0)


def _round(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


def annuity_payment(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """Fixed monthly payment of an annuity mortgage."""
    if months <= 0:
        msg = "months must be positive"
        raise ValueError(msg)
    if principal <= _ZERO:
        return _ZERO
    if annual_rate == _ZERO:
        return _round(principal / months)
    r = annual_rate / 12
    factor = (1 + r) ** -months
    return _round(principal * r / (1 - factor))
