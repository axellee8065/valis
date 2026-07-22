"""공동주택 공시가격 API client (docs/02 §2.1.B).

부동산공시가격알리미 open API via 공공데이터포털. JSON responses.
Published annually (~April); PNU (19-digit parcel number) is the join key
and the preferred base for local_id_canonical v2 (docs/02 §5.1).

Rate limit: ~10 req/s recommended, 5,000/day.
"""

import asyncio

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = structlog.get_logger()

# 공공데이터포털 공동주택 공시가격 조회 서비스
KONGSI_BASE_URL = "https://api.odcloud.kr/api/AptPubPriceService/v1/getAptPubPrice"
RATE_LIMIT_SLEEP_S = 0.1  # 10 req/s
PAGE_SIZE = 100


class KongsiApiError(Exception):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class KongsiClient:
    def __init__(
        self,
        api_key: str,
        http: httpx.AsyncClient | None = None,
        base_url: str = KONGSI_BASE_URL,
    ):
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._base_url = base_url

    async def aclose(self) -> None:
        await self._http.aclose()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=30),
        reraise=True,
    )
    async def _get(self, params: dict) -> dict:
        resp = await self._http.get(self._base_url, params={"serviceKey": self._api_key, **params})
        if resp.status_code == 429:
            log.warning("kongsi_rate_limited", wait_s=60)
            await asyncio.sleep(60)
            resp = await self._http.get(
                self._base_url, params={"serviceKey": self._api_key, **params}
            )
        resp.raise_for_status()
        return resp.json()

    async def fetch_by_pnu(self, pnu: str, year: int) -> list[dict]:
        """All units' official prices for a parcel+year. Raw dicts, un-normalized."""
        payload = await self._get(
            {"pnu": pnu, "stdrYear": str(year), "numOfRows": PAGE_SIZE, "pageNo": 1}
        )
        return extract_items(payload)

    async def fetch_page(self, sgg_cd: str, year: int, page_no: int = 1) -> list[dict]:
        """Page through a district's official prices for bulk backfill."""
        payload = await self._get(
            {
                "sggCd": sgg_cd,
                "stdrYear": str(year),
                "numOfRows": PAGE_SIZE,
                "pageNo": page_no,
            }
        )
        return extract_items(payload)


def extract_items(payload: dict) -> list[dict]:
    """Unwrap the data.go.kr JSON envelope; raises KongsiApiError on API errors."""
    # Envelope variants: {"response": {"header": {...}, "body": {"items": ...}}}
    # or odcloud style: {"data": [...], "currentCount": n}
    if "data" in payload:
        return list(payload["data"])
    response = payload.get("response", {})
    header = response.get("header", {})
    code = str(header.get("resultCode", "")).strip()
    if code and code not in {"00", "000", "0"}:
        raise KongsiApiError(f"{code}: {header.get('resultMsg', '')}")
    items = response.get("body", {}).get("items", [])
    if isinstance(items, dict):  # single-item responses wrap as {"item": {...}|[...]}
        items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
    return list(items)
