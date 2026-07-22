"""공동주택가격 속성조회 API client (docs/02 §2.1.B).

국가중점데이터 (VWorld/국가공간정보포털) — 공동주택가격속성조회:
    https://api.vworld.kr/ned/data/getApartHousingPriceAttr
    params: key (VWorld API key), domain (key 발급 시 등록한 서비스URL — REQUIRED,
    없으면 INCORRECT_KEY), pnu, stdrYear, format=json, numOfRows, pageNo

PNU (19-digit parcel number) is the join key and the preferred base for
local_id_canonical v2 (docs/02 §5.1). Published annually (기준일 1월 1일).

KONGSI_API_KEY in .env holds the VWorld key (issued at vworld.kr, separate
account from data.go.kr).
"""

import asyncio

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = structlog.get_logger()

KONGSI_BASE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
RATE_LIMIT_SLEEP_S = 0.1
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
        api_domain: str = "",
        http: httpx.AsyncClient | None = None,
        base_url: str = KONGSI_BASE_URL,
    ):
        self._api_key = api_key
        self._api_domain = api_domain
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
        merged = {"key": self._api_key, "format": "json", **params}
        if self._api_domain:  # VWorld rejects the key as INCORRECT_KEY without this
            merged["domain"] = self._api_domain
        resp = await self._http.get(self._base_url, params=merged)
        if resp.status_code == 429:
            log.warning("kongsi_rate_limited", wait_s=60)
            await asyncio.sleep(60)
            resp = await self._http.get(self._base_url, params=merged)
        resp.raise_for_status()
        return resp.json()

    async def fetch_by_pnu(self, pnu: str, year: int) -> list[dict]:
        """All units' official prices for a parcel+year. Raw dicts, un-normalized.
        Pages until exhausted (large complexes exceed one page)."""
        items: list[dict] = []
        page_no = 1
        while True:
            payload = await self._get(
                {
                    "pnu": pnu,
                    "stdrYear": str(year),
                    "numOfRows": PAGE_SIZE,
                    "pageNo": page_no,
                }
            )
            batch = extract_items(payload)
            items.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page_no += 1
            await asyncio.sleep(RATE_LIMIT_SLEEP_S)
        return items


def extract_items(payload: dict) -> list[dict]:
    """Unwrap the response envelope; raises KongsiApiError on API errors.

    Envelope variants handled:
    - VWorld ned/data: {"apartHousingPrices": {"totalCount": n, "field": [...]}}
    - VWorld error:    {"error": {"code": ..., "text": ...}} (or nested response)
    - data.go.kr:      {"response": {"header": {...}, "body": {"items": ...}}}
    - odcloud:         {"data": [...]}
    """
    if "error" in payload:
        err = payload["error"]
        if isinstance(err, dict):
            raise KongsiApiError(f"{err.get('code')}: {err.get('text') or err.get('message')}")
        raise KongsiApiError(str(err))

    # VWorld ned/data style — the wrapper key varies by dataset; find "field".
    # Error responses nest resultCode INSIDE the wrapper, e.g.
    # {"apartHousingPrices": {"resultCode": "INCORRECT_KEY", "resultMsg": "..."}}
    for value in payload.values():
        if isinstance(value, dict):
            code = str(value.get("resultCode", "")).strip()
            if code and code not in {"00", "000", "0", "OK", "NORMAL SERVICE"}:
                raise KongsiApiError(f"{code}: {value.get('resultMsg', '')}")
            if "field" in value:
                field = value["field"]
                return [field] if isinstance(field, dict) else list(field)

    if "data" in payload:  # odcloud style
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
