from decimal import Decimal

from packages.adapter_kr.molit.normalizer import (
    canonical_local_id,
    to_property,
    to_transaction,
)
from packages.adapter_kr.molit.xml_parser import parse_apt_trade_response
from packages.core.schemas import PropertyType, TransactionType


def _first(molit_fixture, name="apt_trade_11680_202401.xml"):
    return parse_apt_trade_response(molit_fixture(name)).items[0]


def test_canonical_local_id_format(molit_fixture):
    raw = _first(molit_fixture)
    canonical = canonical_local_id(raw)
    # KR-{sgg(5)}-{umd(5)}-{land}-{bonbun(4)}-{bubun(4)}-{dong}-{floor}-{area*100}
    assert canonical == "KR-11680-10800-1-0045-0000-A-12-8499"


def test_canonical_is_stable_across_transactions(molit_fixture):
    """Same unit in different trades must map to the same canonical ID."""
    raw = _first(molit_fixture)
    cancelled = _first(molit_fixture, "apt_trade_cancelled.xml")
    # Different floors → different canonical (unit-level identity)
    assert canonical_local_id(raw) != canonical_local_id(cancelled)


def test_to_transaction_normal(molit_fixture):
    raw = _first(molit_fixture)
    tx = to_transaction(raw, fx_krw_usd=Decimal("0.00072"))

    assert tx.transaction_type == TransactionType.SALE
    assert str(tx.transaction_date) == "2024-01-15"
    assert tx.price_original_amount == Decimal(1_250_000_000)  # 125,000만원
    assert tx.price_original_currency == "KRW"
    assert tx.price_usd_cents == 90_000_000  # $900k
    assert tx.is_cancelled is False
    assert tx.is_related_party is False
    assert str(tx.registration_date) == "2024-02-20"
    assert tx.source == "MOLIT_APT_TRADE"
    assert tx.raw_payload["dealAmount"] == "125,000"


def test_to_transaction_without_fx(molit_fixture):
    tx = to_transaction(_first(molit_fixture))
    assert tx.price_usd_cents is None
    assert tx.fx_rate_at_date is None


def test_to_transaction_cancelled(molit_fixture):
    raw = _first(molit_fixture, "apt_trade_cancelled.xml")
    tx = to_transaction(raw)
    assert tx.is_cancelled is True
    assert str(tx.cancelled_at) == "2024-01-20"
    assert tx.is_related_party is True  # 직거래


def test_complex_id_prefers_apt_seq(molit_fixture):
    """aptSeq present → stable MOLIT complex key; absent → name-based fallback."""
    page = parse_apt_trade_response(molit_fixture("apt_trade_11680_202401.xml"))
    with_seq, without_seq = page.items[0], page.items[1]
    assert to_property(with_seq).complex_id == "KR-APT-11680-123"
    assert to_property(without_seq).complex_id == "KR-11680-10800-역삼래미안"


def test_to_property(molit_fixture):
    raw = _first(molit_fixture)
    prop = to_property(raw)

    assert prop.country_code == "KR"
    assert prop.property_type == PropertyType.APARTMENT
    assert prop.admin_level_1 == "서울특별시"
    assert prop.admin_level_2 == "강남구"
    assert prop.admin_level_3 == "역삼동"
    assert prop.net_area_sqm == Decimal("84.99")
    assert prop.built_year == 2015
    assert prop.floor_number == 12
    assert prop.complex_name == "역삼래미안"
    assert "Gangnam-gu" in prop.address_normalized
    assert prop.global_id.startswith("0x")


def test_transaction_and_property_share_global_id(molit_fixture):
    raw = _first(molit_fixture)
    assert to_transaction(raw).global_id == to_property(raw).global_id


def test_source_record_id_idempotency(molit_fixture):
    """Same record parsed twice → same idempotency key (safe re-runs)."""
    a = to_transaction(_first(molit_fixture))
    b = to_transaction(_first(molit_fixture))
    assert a.source_record_id == b.source_record_id
