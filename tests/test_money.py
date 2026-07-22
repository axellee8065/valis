from decimal import Decimal

from packages.core.money import krw_man_to_krw, to_usd_cents


def test_krw_man_parsing_with_commas():
    assert krw_man_to_krw("12,500") == 125_000_000
    assert krw_man_to_krw("1,250") == 12_500_000
    assert krw_man_to_krw(100) == 1_000_000


def test_to_usd_cents():
    # 1,250,000,000 KRW at 0.00072 USD/KRW = $900,000 = 90,000,000 cents
    assert to_usd_cents(1_250_000_000, Decimal("0.00072")) == 90_000_000


def test_to_usd_cents_rounds_half_up():
    assert to_usd_cents(1, Decimal("0.005")) == 1  # 0.5 cents → 1
