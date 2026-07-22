"""Ingest KRW/USD daily FX rates from BOK ECOS into fx_rates.

Usage:
    python scripts/ingest_fx.py --from 2020-01-01 --to 2026-07-23

Run BEFORE (or re-run after) ingest_molit so transactions get USD normalization.
Idempotent via (currency, rate_date) unique constraint.
"""

import argparse
import asyncio
from datetime import date

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.adapter_kr.fx.ecos_client import EcosClient
from packages.core.config import get_settings
from packages.core.db.models import FxRateRow
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

SOURCE = "BOK_ECOS_731Y001"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.bok_ecos_key:
        raise SystemExit("BOK_ECOS_KEY not set in .env")

    client = EcosClient(settings.bok_ecos_key)
    try:
        rates = await client.fetch_krw_usd_rates(
            date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
        )
    finally:
        await client.aclose()

    async with get_session_factory()() as session:
        for r in rates:
            stmt = (
                pg_insert(FxRateRow)
                .values(
                    currency="KRW",
                    rate_date=r.rate_date,
                    usd_per_unit=r.usd_per_krw,
                    source=SOURCE,
                )
                .on_conflict_do_update(
                    constraint="uq_fx_ccy_date",
                    set_={"usd_per_unit": r.usd_per_krw, "source": SOURCE},
                )
            )
            await session.execute(stmt)
        await session.commit()
    log.info("fx_ingest_done", rows=len(rates))


if __name__ == "__main__":
    asyncio.run(main())
