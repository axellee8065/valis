"""MOLIT 실거래가 HTTP client with retry/rate-limit handling
(docs/02-korea-adapter.md §2.1.A, §6).

- 5xx → exponential backoff, 3 attempts
- 429 → wait 60s
- 4xx (other) → log and raise immediately
"""

import asyncio

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from packages.adapter_kr.molit.xml_parser import (
    AptTradePage,
    parse_apt_trade_response,
)

log = structlog.get_logger()

APT_TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
MAX_ROWS_PER_PAGE = 1000
RATE_LIMIT_SLEEP_S = 0.05  # ~20 req/s, safety margin under the 30/s dev quota


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class MolitClient:
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
        resp = await self._http.get(APT_TRADE_URL, params=params)
        if resp.status_code == 429:
            log.warning("molit_rate_limited", wait_s=60)
            await asyncio.sleep(60)
            resp = await self._http.get(APT_TRADE_URL, params=params)
        resp.raise_for_status()
        return resp.content

    async def fetch_apt_trades_page(
        self, lawd_cd: str, deal_ymd: str, page_no: int = 1
    ) -> AptTradePage:
        """One page of apartment sale records for a district+month.

        lawd_cd: 5-digit legal district code; deal_ymd: YYYYMM.
        """
        raw = await self._get(
            {
                "serviceKey": self._api_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "numOfRows": MAX_ROWS_PER_PAGE,
                "pageNo": page_no,
            }
        )
        return parse_apt_trade_response(raw)

    async def fetch_apt_trades(self, lawd_cd: str, deal_ymd: str):
        """Iterate all pages for a district+month, respecting rate limits."""
        page_no = 1
        while True:
            page = await self.fetch_apt_trades_page(lawd_cd, deal_ymd, page_no)
            for item in page.items:
                yield item
            if page.page_no * page.num_of_rows >= page.total_count or not page.items:
                break
            page_no += 1
            await asyncio.sleep(RATE_LIMIT_SLEEP_S)
