"""Currency normalization utilities.

All protocol money is stored as USD cents (int). Original amounts and the FX
rate applied at the transaction date are always stored alongside.
"""

from decimal import ROUND_HALF_UP, Decimal

# 만원 → 원
KRW_MAN_WON = 10_000


def krw_man_to_krw(deal_amount_man: str | int) -> int:
    """MOLIT dealAmount comes as '12,500' (unit: 만원)."""
    if isinstance(deal_amount_man, str):
        deal_amount_man = int(deal_amount_man.replace(",", "").strip())
    return deal_amount_man * KRW_MAN_WON


def to_usd_cents(original_amount: Decimal | int, fx_rate_to_usd: Decimal) -> int:
    """Convert an original-currency amount to USD cents.

    fx_rate_to_usd: USD per 1 unit of original currency
    (e.g. KRW→USD ≈ 0.00072). Rounded half-up to the nearest cent.
    """
    amount = Decimal(original_amount)
    usd = amount * fx_rate_to_usd
    cents = (usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)
