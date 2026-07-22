"""한국은행 ECOS OpenAPI client — KRW/USD 매매기준율 (docs/02 §5.3).

API: https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{start}/{end}/{stat}/{cycle}/{from}/{to}/{item}
- STAT_CODE 731Y001: 주요국 통화의 대원화 환율
- ITEM_CODE 0000001: 원/미국달러(매매기준율)
- CYCLE D: daily

Response gives KRW per USD ("1,320.5"); we store USD per KRW = 1/rate.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
import structlog

log = structlog.get_logger()

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
STAT_KRW_USD = "731Y001"
ITEM_KRW_USD = "0000001"
PAGE_SIZE = 1000


class EcosApiError(Exception):
    pass


@dataclass(frozen=True)
class DailyRate:
    rate_date: date
    usd_per_krw: Decimal
    krw_per_usd: Decimal


def parse_ecos_rows(payload: dict) -> list[DailyRate]:
    """Parse a StatisticSearch JSON payload into daily rates.

    Rows carry TIME='YYYYMMDD' and DATA_VALUE='1,320.5' (KRW per USD).
    Rows with empty DATA_VALUE (holidays echoed by some cycles) are skipped.
    """
    if "RESULT" in payload:  # error envelope: {"RESULT": {"CODE": ..., "MESSAGE": ...}}
        result = payload["RESULT"]
        raise EcosApiError(f"{result.get('CODE')}: {result.get('MESSAGE')}")
    body = payload.get("StatisticSearch")
    if body is None:
        raise EcosApiError(f"unexpected ECOS payload keys: {list(payload)}")

    rates: list[DailyRate] = []
    for row in body.get("row", []):
        t = (row.get("TIME") or "").strip()
        v = (row.get("DATA_VALUE") or "").strip().replace(",", "")
        if len(t) != 8 or not v:
            continue
        krw_per_usd = Decimal(v)
        if krw_per_usd <= 0:
            continue
        rates.append(
            DailyRate(
                rate_date=date(int(t[:4]), int(t[4:6]), int(t[6:8])),
                usd_per_krw=(Decimal(1) / krw_per_usd).quantize(Decimal("0.0000000001")),
                krw_per_usd=krw_per_usd,
            )
        )
    return rates


class EcosClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch_krw_usd_rates(self, start: date, end: date) -> list[DailyRate]:
        """All daily KRW/USD rates in [start, end], paging as needed."""
        rates: list[DailyRate] = []
        page_start = 1
        while True:
            page_end = page_start + PAGE_SIZE - 1
            url = (
                f"{ECOS_BASE}/{self._api_key}/json/kr/{page_start}/{page_end}/"
                f"{STAT_KRW_USD}/D/{start:%Y%m%d}/{end:%Y%m%d}/{ITEM_KRW_USD}"
            )
            resp = await self._http.get(url)
            resp.raise_for_status()
            batch = parse_ecos_rows(resp.json())
            rates.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page_start += PAGE_SIZE
        log.info("ecos_rates_fetched", count=len(rates), start=str(start), end=str(end))
        return rates
