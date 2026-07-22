"""세움터 표제부 record → property enrichment fields (docs/02 §2.1.C).

The building register enriches MOLIT-derived Property rows with fields the
trade feed lacks: units_in_building, floors_total, building_area, structure,
parking. Returned as a partial-update dict keyed by our schema names.
"""

from datetime import date

import structlog

log = structlog.get_logger()

# 주용도 코드 → property master hints (표제부 mainPurpsCd)
APT_MAIN_PURPS_CODES = {"02001"}  # 아파트

# 구조코드 매핑 (strctCd) — kept as raw code + name for AVM categorical use
KNOWN_STRUCTURES = {
    "11": "벽돌구조",
    "12": "블록구조",
    "21": "철근콘크리트구조",  # RC
    "22": "프리케스트콘크리트구조",
    "31": "철골구조",
    "41": "철골철근콘크리트구조",  # SRC
}


def _to_int(value: str | None) -> int | None:
    txt = str(value or "").replace(",", "").strip()
    if not txt or not txt.lstrip("-").isdigit():
        return None
    return int(txt)


def _to_float(value: str | None) -> float | None:
    txt = str(value or "").replace(",", "").strip()
    try:
        return float(txt) if txt else None
    except ValueError:
        return None


def _approval_year(use_apr_day: str | None) -> int | None:
    txt = str(use_apr_day or "").replace("-", "").replace(".", "").strip()
    if len(txt) >= 4 and txt[:4].isdigit():
        year = int(txt[:4])
        if 1900 <= year <= date.today().year:
            return year
    return None


def to_property_enrichment(raw: dict) -> dict:
    """Map a 표제부 record to Property partial-update fields.

    Only returns keys with usable values — caller merges into the property
    row without clobbering existing data (COALESCE semantics).
    """
    hhld = _to_int(raw.get("hhldCnt"))
    grnd = _to_int(raw.get("grndFlrCnt"))
    tot_area = _to_float(raw.get("totArea"))
    built = _approval_year(raw.get("useAprDay"))
    parking = sum(
        v
        for v in (
            _to_int(raw.get("indrAutoUtcnt")),  # 옥내 자주식
            _to_int(raw.get("oudrAutoUtcnt")),  # 옥외 자주식
            _to_int(raw.get("indrMechUtcnt")),  # 옥내 기계식
            _to_int(raw.get("oudrMechUtcnt")),  # 옥외 기계식
        )
        if v is not None
    )

    enrichment: dict = {}
    if hhld:
        enrichment["units_in_building"] = hhld
    if grnd:
        enrichment["floors_total"] = grnd
    if tot_area:
        enrichment["building_area_sqm"] = tot_area
    if built:
        enrichment["built_year"] = built
    if parking:
        enrichment["parking_spaces"] = parking

    strct_cd = str(raw.get("strctCd") or "").strip()
    if strct_cd:
        enrichment["property_subtype"] = KNOWN_STRUCTURES.get(
            strct_cd, raw.get("strctCdNm") or strct_cd
        )
    return enrichment


def is_apartment(raw: dict) -> bool:
    """True if the building register marks this as 아파트."""
    code = str(raw.get("mainPurpsCd") or "").strip()
    if code:
        return code in APT_MAIN_PURPS_CODES
    return "아파트" in str(raw.get("mainPurpsCdNm") or "")
