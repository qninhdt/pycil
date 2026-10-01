"""Usage unit and pricing conversion.

Authoritative internal usage metering representation uses 64-bit integer units:
    1 allowance unit = 1,000 internal usage units
    1 internal usage unit = $0.000001 USD

Python calculations use Decimal arithmetic and quantize to integer units exactly once.
"""

from decimal import ROUND_HALF_UP, Decimal

UNITS_PER_ALLOWANCE_UNIT = 1_000
USD_PER_ALLOWANCE_UNIT = Decimal("0.001")


def usd_to_units(usd_amount: Decimal) -> int:
    """Convert a total USD cost to internal integer usage units with single ROUND_HALF_UP."""
    if usd_amount <= Decimal("0"):
        return 0
    units = (usd_amount / USD_PER_ALLOWANCE_UNIT * Decimal(UNITS_PER_ALLOWANCE_UNIT)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return max(0, int(units))


def allowance_to_units(allowance: int | Decimal | str) -> int:
    """Convert allowance quantity to internal integer usage units."""
    dec = Decimal(str(allowance))
    if dec <= Decimal("0"):
        return 0
    scaled = dec * Decimal(UNITS_PER_ALLOWANCE_UNIT)
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def units_to_allowance(units: int) -> Decimal:
    """Convert internal integer usage units to allowance quantity."""
    return Decimal(units) / Decimal(UNITS_PER_ALLOWANCE_UNIT)
