"""MOLIT 실거래가 XML response parser (docs/02-korea-adapter.md §2.1.A).

MOLIT returns XML only (no JSON). Numeric fields arrive as strings, sometimes
with commas ("12,500"). This module only parses — normalization lives in
normalizer.py.
"""

from dataclasses import dataclass, field

from lxml import etree

RESULT_OK = {"00", "000"}


class MolitApiError(Exception):
    def __init__(self, result_code: str, result_msg: str):
        self.result_code = result_code
        self.result_msg = result_msg
        super().__init__(f"MOLIT API error {result_code}: {result_msg}")


class MolitParseError(Exception):
    """Malformed XML — caller should store raw payload and dead-letter it."""


@dataclass(frozen=True)
class RawAptTrade:
    """One <item> from getRTMSDataSvcAptTradeDev, verbatim strings."""

    sgg_cd: str  # 시군구코드 (5)
    umd_cd: str  # 읍면동코드
    apt_seq: str  # MOLIT 단지 일련번호 (e.g. "11680-381") — stable complex key
    umd_nm: str  # 읍면동명
    land_cd: str  # 지번코드
    bonbun: str  # 본번
    bubun: str  # 부번
    road_nm: str  # 도로명
    apt_nm: str  # 아파트명
    apt_dong: str  # 동
    floor: str  # 층
    exclu_use_ar: str  # 전용면적 ㎡
    deal_amount: str  # 거래금액 만원, 쉼표 포함
    deal_year: str
    deal_month: str
    deal_day: str
    build_year: str  # 건축년도
    cdeal_type: str  # 해제여부 ("O" = cancelled)
    cdeal_day: str  # 해제사유발생일
    dealing_gbn: str  # 거래유형 (직거래/중개거래)
    rgst_date: str  # 등기일자
    raw: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class AptTradePage:
    items: list[RawAptTrade]
    total_count: int
    page_no: int
    num_of_rows: int


_FIELD_MAP = {
    "sggCd": "sgg_cd",
    "umdCd": "umd_cd",
    "aptSeq": "apt_seq",
    "umdNm": "umd_nm",
    "landCd": "land_cd",
    "bonbun": "bonbun",
    "bubun": "bubun",
    "roadNm": "road_nm",
    "aptNm": "apt_nm",
    "aptDong": "apt_dong",
    "floor": "floor",
    "excluUseAr": "exclu_use_ar",
    "dealAmount": "deal_amount",
    "dealYear": "deal_year",
    "dealMonth": "deal_month",
    "dealDay": "deal_day",
    "buildYear": "build_year",
    "cdealType": "cdeal_type",
    "cdealDay": "cdeal_day",
    "dealingGbn": "dealing_gbn",
    "rgstDate": "rgst_date",
}


def _text(el: etree._Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_apt_trade_response(xml_bytes: bytes) -> AptTradePage:
    """Parse a full response page. Raises MolitApiError on non-OK resultCode,
    MolitParseError on malformed XML."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise MolitParseError(str(exc)) from exc

    result_code = root.findtext(".//resultCode", default="").strip()
    result_msg = root.findtext(".//resultMsg", default="").strip()
    if result_code not in RESULT_OK:
        raise MolitApiError(result_code, result_msg)

    items: list[RawAptTrade] = []
    for item_el in root.findall(".//items/item"):
        raw = {child.tag: (child.text or "").strip() for child in item_el}
        kwargs = {attr: _text(item_el, tag) for tag, attr in _FIELD_MAP.items()}
        items.append(RawAptTrade(**kwargs, raw=raw))

    def _int(tag: str, default: int = 0) -> int:
        txt = root.findtext(f".//{tag}", default="").strip()
        return int(txt) if txt.isdigit() else default

    return AptTradePage(
        items=items,
        total_count=_int("totalCount"),
        page_no=_int("pageNo", 1),
        num_of_rows=_int("numOfRows", len(items)),
    )
