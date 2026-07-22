"""Seed Seoul legal-dong district codes (M1 setup).

The 25-gu master lives in code (packages/adapter_kr/geo/legal_dong_codes.py);
this script just verifies DB connectivity and prints the roster. Full 법정동
(dong-level) code ingestion from MOIS lands with the 세움터 integration.
"""

import asyncio

from sqlalchemy import text

from packages.adapter_kr.geo.legal_dong_codes import SEOUL_GU_CODES
from packages.core.db.session import get_session_factory


async def main() -> None:
    async with get_session_factory()() as session:
        await session.execute(text("SELECT 1"))
    print(f"DB reachable. Seoul districts registered in code: {len(SEOUL_GU_CODES)}")
    for code, name in SEOUL_GU_CODES.items():
        print(f"  {code}  {name}")


if __name__ == "__main__":
    asyncio.run(main())
