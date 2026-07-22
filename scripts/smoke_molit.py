"""Daily live smoke test — detects MOLIT API spec changes (docs/02 §7).

Fetches one page for 강남구, previous month, and asserts known fields exist.
Run by CI on schedule; fails loudly if the API drifts.
"""

import asyncio
import sys
from datetime import date

from packages.adapter_kr.molit.client import MolitClient
from packages.core.config import get_settings

REQUIRED_FIELDS = ["sggCd", "excluUseAr", "dealAmount", "dealYear", "aptNm"]


async def main() -> int:
    today = date.today()
    prev = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    ymd = f"{prev.year}{prev.month:02d}"

    client = MolitClient(get_settings().molit_api_key)
    try:
        page = await client.fetch_apt_trades_page("11680", ymd)
    finally:
        await client.aclose()

    if not page.items:
        print(f"WARN: no trades returned for 11680/{ymd} (holiday month?)")
        return 0

    sample = page.items[0].raw
    missing = [f for f in REQUIRED_FIELDS if f not in sample]
    if missing:
        print(f"FAIL: MOLIT spec drift — missing fields: {missing}")
        return 1
    print(f"OK: {page.total_count} trades for 11680/{ymd}; fields intact")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
