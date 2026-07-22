"""공시가격 raw record → GovernmentValuation (docs/02 §2.1.B).

Key raw fields: pnu (19자리), pblntfPc (공시가격, 원), stdrYear,
dongNm/hoNm (동·호), prvuseAr (전용면적).

VWorld 속성조회 responses carry stdrYear but no 공시일자 field — the legal
기준일 for 공동주택 공시가격 is January 1 of the assessment year, so we use
that when pblntfDe is absent.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.core.money import to_usd_cents
from packages.core.schemas import GovernmentValuation

SOURCE_AUTHORITY = "국토교통부 부동산공시가격알리미"
VALUATION_TYPE_APT = "KR_APT_KONGSI"


class KongsiRecordError(ValueError):
    """Record missing required fields — dead-letter it, don't crash the batch."""


def _clean_int(value) -> int:
    if value is None:
        raise KongsiRecordError("missing numeric value")
    if isinstance(value, (int, float)):
        return int(value)
    txt = str(value).replace(",", "").strip()
    if not txt or not txt.lstrip("-").isdigit():
        raise KongsiRecordError(f"non-numeric value: {value!r}")
    return int(txt)


def _parse_date(value) -> date:
    txt = str(value or "").replace("-", "").replace(".", "").strip()
    if len(txt) != 8 or not txt.isdigit():
        raise KongsiRecordError(f"bad date: {value!r}")
    return date(int(txt[:4]), int(txt[4:6]), int(txt[6:8]))


def parse_pnu(pnu: str) -> dict:
    """Split a 19-digit PNU into components.

    PNU = 시군구(5) + 읍면동리(5) + 필지구분(1) + 본번(4) + 부번(4)
    """
    pnu = str(pnu).strip()
    if len(pnu) != 19 or not pnu.isdigit():
        raise KongsiRecordError(f"invalid PNU: {pnu!r}")
    return {
        "sgg_cd": pnu[:5],
        "umd_cd": pnu[5:10],
        "land_cd": pnu[10],
        "bonbun": pnu[11:15],
        "bubun": pnu[15:19],
    }


def to_government_valuation(
    raw: dict,
    global_id: str,
    fx_krw_usd: Decimal,
    ingested_at: datetime | None = None,
) -> GovernmentValuation:
    """Normalize one 공시가격 record.

    The caller resolves global_id by PNU-matching against the property master
    (parse_pnu → canonical components). fx is required: 공시가격 is annual and
    the assessment-date rate is always available by ingestion time.
    """
    price_krw = _clean_int(raw.get("pblntfPc"))
    year = raw.get("stdrYear")
    if raw.get("pblntfDe"):
        assessment_date = _parse_date(raw.get("pblntfDe"))
        assessment_year = _clean_int(year) if year else assessment_date.year
    elif year:
        assessment_year = _clean_int(year)
        assessment_date = date(assessment_year, 1, 1)  # 공시 기준일
    else:
        raise KongsiRecordError("record has neither pblntfDe nor stdrYear")

    return GovernmentValuation(
        global_id=global_id,
        valuation_type=VALUATION_TYPE_APT,
        assessment_year=assessment_year,
        assessment_date=assessment_date,
        value_usd_cents=to_usd_cents(price_krw, fx_krw_usd),
        value_original_amount=Decimal(price_krw),
        value_original_currency="KRW",
        fx_rate_at_date=fx_krw_usd,
        source_authority=SOURCE_AUTHORITY,
        raw_payload=raw,
        ingested_at=ingested_at or datetime.now(UTC),
    )
