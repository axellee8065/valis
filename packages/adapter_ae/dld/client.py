"""DLD open-data gateway client (live top-up path).

The DLD portal exposes an unauthenticated JSON API used by its own open-data
page:  POST https://gateway.dubailand.gov.ae/open-data/{command}
with a filter body + P_TAKE/P_SKIP paging (reverse-engineered from
dubailand.gov.ae/scripts/api/OpenDataApi.js + publicData.js).

As of 2026-07 the gateway intermittently 500s (Dubai Pulse down as well) —
bulk history comes from the mirror parquet (scripts/ingest_dld.py --parquet);
this client exists to top up recent months once the backend recovers.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx

GATEWAY_URL = "https://gateway.dubailand.gov.ae/open-data"
PAGE_SIZE = 500


class DldClient:
    def __init__(self, timeout_s: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) valis/0.1",
                "Origin": "https://dubailand.gov.ae",
                "Referer": "https://dubailand.gov.ae/en/open-data/real-estate-data/",
            },
        )

    async def fetch_transactions(
        self, from_date: str, to_date: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw transaction rows for a DD/MM/YYYY date range."""
        skip = 0
        while True:
            body = {
                "P_FROM_DATE": from_date,
                "P_TO_DATE": to_date,
                "P_GROUP_ID": "",
                "P_IS_OFFPLAN": "",
                "P_IS_FREE_HOLD": "",
                "P_AREA_ID": "",
                "P_USAGE_ID": "",
                "P_PROP_TYPE_ID": "",
                "P_TAKE": str(PAGE_SIZE),
                "P_SKIP": str(skip),
                "P_SORT": "TRANSACTION_NUMBER_ASC",
            }
            resp = await self._client.post(f"{GATEWAY_URL}/transactions", json=body)
            resp.raise_for_status()
            payload = resp.json()
            rows = (payload.get("response") or {}).get("result") or []
            if not rows:
                return
            for row in rows:
                yield row
            if len(rows) < PAGE_SIZE:
                return
            skip += PAGE_SIZE

    async def aclose(self) -> None:
        await self._client.aclose()
