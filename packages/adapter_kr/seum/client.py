"""세움터 건축물대장 API client (docs/02 §2.1.C).

getBrTitleInfo (표제부): building-level master — total area, approval date,
structure, household count, floor counts. XML responses, PNU-component params.

Rate limit: 30 req/s, 10,000/day (dev key).
"""

import asyncio

import httpx
import structlog
from lxml import etree
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = structlog.get_logger()

TITLE_INFO_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrTitleInfo"
RATE_LIMIT_SLEEP_S = 0.05
RESULT_OK = {"00", "000"}


class SeumApiError(Exception):
    def __init__(self, result_code: str, result_msg: str):
        self.result_code = result_code
        self.result_msg = result_msg
        super().__init__(f"Seum API error {result_code}: {result_msg}")


class SeumParseError(Exception):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def parse_title_info(xml_bytes: bytes) -> list[dict]:
    """Parse getBrTitleInfo XML into raw dicts (one per building)."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise SeumParseError(str(exc)) from exc

    code = (root.findtext(".//resultCode") or "").strip()
    msg = (root.findtext(".//resultMsg") or "").strip()
    if code not in RESULT_OK:
        raise SeumApiError(code, msg)

    return [
        {child.tag: (child.text or "").strip() for child in item}
        for item in root.findall(".//items/item")
    ]


class SeumClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=30),
        reraise=True,
    )
    async def _get(self, params: dict) -> bytes:
        resp = await self._http.get(TITLE_INFO_URL, params=params)
        if resp.status_code == 429:
            log.warning("seum_rate_limited", wait_s=60)
            await asyncio.sleep(60)
            resp = await self._http.get(TITLE_INFO_URL, params=params)
        resp.raise_for_status()
        return resp.content

    async def fetch_title_info(
        self, sgg_cd: str, umd_cd: str, bun: str, ji: str, plat_gb_cd: str = "0"
    ) -> list[dict]:
        """표제부 for a parcel. Params mirror PNU components:
        sgg_cd(5) + umd_cd(5) as bjdongCd, bun/ji zero-padded to 4."""
        raw = await self._get(
            {
                "serviceKey": self._api_key,
                "sigunguCd": sgg_cd,
                "bjdongCd": umd_cd,
                "platGbCd": plat_gb_cd,
                "bun": f"{bun:0>4}",
                "ji": f"{ji:0>4}",
                "numOfRows": 100,
                "pageNo": 1,
                "_type": "xml",
            }
        )
        return parse_title_info(raw)
