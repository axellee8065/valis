"""RawAptTrade → normalized Transaction / Property (docs/02-korea-adapter.md §5).

Canonical local ID rule (NEVER change — global_id depends on it):
    KR-{sggCd(5)}-{umdCd(5)}-{landCd(1)}-{bonbun(4)}-{bubun(4)}-{aptDong or ""}-{floor}-{net_area_sqm×100}
Example: KR-11680-10800-1-0045-0000-A-12-8499
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.adapter_kr.geo.address_normalizer import normalize_address
from packages.adapter_kr.geo.legal_dong_codes import SEOUL_GU_CODES
from packages.adapter_kr.molit.xml_parser import RawAptTrade
from packages.core.ids import make_global_id
from packages.core.money import krw_man_to_krw, to_usd_cents
from packages.core.schemas import (
    DataSourceRef,
    OwnershipType,
    Property,
    PropertyType,
    Transaction,
    TransactionType,
)

SOURCE_APT_TRADE = "MOLIT_APT_TRADE"


def canonical_local_id(raw: RawAptTrade) -> str:
    """Deterministic canonical ID for a single apartment unit."""
    net_area_x100 = round(float(raw.exclu_use_ar) * 100)
    dong = raw.apt_dong.strip().upper()  # 결측 시 빈 문자열 (documented)
    return (
        f"KR-{raw.sgg_cd:0>5}-{raw.umd_cd:0>5}-{raw.land_cd}"
        f"-{raw.bonbun:0>4}-{raw.bubun:0>4}-{dong}-{int(raw.floor or 0)}-{net_area_x100}"
    )


def raw_local_id(raw: RawAptTrade) -> str:
    return f"{raw.sgg_cd}{raw.umd_cd}-{raw.land_cd}-{raw.bonbun}-{raw.bubun}"


def source_record_id(raw: RawAptTrade) -> str:
    """Idempotency key within MOLIT source: unit + deal date + amount."""
    ymd = f"{raw.deal_year}{raw.deal_month:0>2}{raw.deal_day:0>2}"
    amount = raw.deal_amount.replace(",", "")
    return f"{canonical_local_id(raw)}@{ymd}#{amount}"


def _deal_date(raw: RawAptTrade) -> date:
    return date(int(raw.deal_year), int(raw.deal_month), int(raw.deal_day))


def _parse_compact_date(txt: str) -> date | None:
    """'24.01.15' or '20240115' or '' → date | None."""
    txt = txt.strip()
    if not txt:
        return None
    txt = txt.replace(".", "").replace("-", "")
    if len(txt) == 6:  # YY MMDD
        txt = "20" + txt
    if len(txt) != 8 or not txt.isdigit():
        return None
    return date(int(txt[:4]), int(txt[4:6]), int(txt[6:8]))


def to_transaction(
    raw: RawAptTrade,
    fx_krw_usd: Decimal | None = None,
    ingested_at: datetime | None = None,
) -> Transaction:
    """Normalize one MOLIT apartment-sale record.

    - dealAmount '12,500' 만원 → KRW int → USD cents (if FX known)
    - cdealType == 'O' → is_cancelled (kept, filtered at analysis time)
    - dealingGbn '직거래' → is_related_party candidate flag
    """
    krw = krw_man_to_krw(raw.deal_amount)
    cancelled = raw.cdeal_type.strip().upper() == "O"
    global_id = make_global_id("KR", canonical_local_id(raw))

    return Transaction(
        global_id=global_id,
        transaction_type=TransactionType.SALE,
        transaction_date=_deal_date(raw),
        contract_date=_deal_date(raw),  # 실거래가는 계약일 기준
        registration_date=_parse_compact_date(raw.rgst_date),
        price_usd_cents=to_usd_cents(krw, fx_krw_usd) if fx_krw_usd else None,
        price_original_amount=Decimal(krw),
        price_original_currency="KRW",
        fx_rate_at_date=fx_krw_usd,
        is_verified=True,
        is_cancelled=cancelled,
        cancelled_at=_parse_compact_date(raw.cdeal_day) if cancelled else None,
        is_related_party=raw.dealing_gbn.strip() == "직거래",
        source=SOURCE_APT_TRADE,
        source_record_id=source_record_id(raw),
        raw_payload=raw.raw,
        ingested_at=ingested_at or datetime.now(UTC),
    )


def to_property(raw: RawAptTrade, ingested_at: datetime | None = None) -> Property:
    """Build the normalized Property reference from a trade record."""
    now = ingested_at or datetime.now(UTC)
    canonical = canonical_local_id(raw)
    gu = SEOUL_GU_CODES.get(raw.sgg_cd, "")
    original_addr = " ".join(
        p for p in ["서울특별시", gu, raw.umd_nm, raw.road_nm, raw.bonbun.lstrip("0")] if p
    )
    normalized_addr, _ = normalize_address(original_addr)
    complex_id = f"KR-{raw.sgg_cd}-{raw.umd_cd}-{raw.apt_nm}".replace(" ", "")

    return Property(
        global_id=make_global_id("KR", canonical),
        country_code="KR",
        local_id=raw_local_id(raw),
        local_id_canonical=canonical,
        property_type=PropertyType.APARTMENT,
        address_normalized=normalized_addr,
        address_original=original_addr,
        admin_level_1="서울특별시",
        admin_level_2=gu or None,
        admin_level_3=raw.umd_nm or None,
        net_area_sqm=Decimal(raw.exclu_use_ar),
        built_year=int(raw.build_year) if raw.build_year.isdigit() else None,
        floor_number=int(raw.floor) if raw.floor.lstrip("-").isdigit() else None,
        ownership_type=OwnershipType.STRATA,
        complex_id=complex_id,
        complex_name=raw.apt_nm or None,
        data_sources=[
            DataSourceRef(
                source=SOURCE_APT_TRADE,
                fetched_at=now,
                raw_id=source_record_id(raw),
            )
        ],
        created_at=now,
        updated_at=now,
    )
