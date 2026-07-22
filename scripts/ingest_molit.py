"""Bulk/incremental MOLIT ingestion (docs/02 §4).

Usage:
    python scripts/ingest_molit.py --region seoul --from 2020-01 --to 2024-12
    python scripts/ingest_molit.py --gu 11680 --from 2024-01 --to 2024-03

Idempotent: (source, source_record_id) unique constraint makes re-runs safe.
Cancelled trades are stored with is_cancelled=true — never deleted.
"""

import argparse
import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.adapter_kr.geo.legal_dong_codes import SEOUL_GU_CODES
from packages.adapter_kr.molit.client import RATE_LIMIT_SLEEP_S, MolitClient
from packages.adapter_kr.molit.normalizer import to_property, to_transaction
from packages.adapter_kr.molit.xml_parser import MolitParseError
from packages.core.config import get_settings
from packages.core.db.models import PropertyRow, TransactionRow
from packages.core.db.session import get_session_factory
from packages.core.fx import FxProvider

log = structlog.get_logger()


def month_range(start: str, end: str) -> list[str]:
    """'2020-01'..'2024-12' → ['202001', ..., '202412']"""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return months


async def ingest_month(
    client: MolitClient, session_factory, gu_code: str, ymd: str, fx: FxProvider | None = None
) -> dict:
    stats = {"fetched": 0, "cancelled": 0, "parse_errors": 0, "no_fx": 0}
    async with session_factory() as session:
        try:
            async for raw in client.fetch_apt_trades(gu_code, ymd):
                now = datetime.now(UTC)
                deal_date = f"{raw.deal_year}-{int(raw.deal_month):02d}-{int(raw.deal_day):02d}"
                fx_rate = fx.rate_at(deal_date) if fx else None
                if fx and fx_rate is None:
                    stats["no_fx"] += 1
                tx = to_transaction(raw, fx_krw_usd=fx_rate, ingested_at=now)
                prop = to_property(raw, ingested_at=now)

                prop_values = prop.model_dump(mode="json")
                prop_stmt = pg_insert(PropertyRow).values(**prop_values)
                prop_stmt = prop_stmt.on_conflict_do_update(
                    index_elements=["global_id"],
                    set_={"updated_at": now, "data_sources": prop_values["data_sources"]},
                )
                await session.execute(prop_stmt)

                tx_stmt = pg_insert(TransactionRow).values(**tx.model_dump(mode="json"))
                # Re-reported records: latest wins on cancellation flags
                tx_stmt = tx_stmt.on_conflict_do_update(
                    index_elements=["source", "source_record_id"],
                    set_={
                        "is_cancelled": tx.is_cancelled,
                        "cancelled_at": tx.cancelled_at,
                        "registration_date": tx.registration_date,
                        "ingested_at": now,
                    },
                )
                await session.execute(tx_stmt)

                stats["fetched"] += 1
                stats["cancelled"] += int(tx.is_cancelled)
        except MolitParseError as exc:
            stats["parse_errors"] += 1
            log.error("molit_parse_error", gu=gu_code, ymd=ymd, error=str(exc))
        await session.commit()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest MOLIT apartment trades")
    parser.add_argument("--region", choices=["seoul"], default=None)
    parser.add_argument("--gu", help="single 5-digit LAWD_CD")
    parser.add_argument("--from", dest="from_month", required=True, help="YYYY-MM")
    parser.add_argument("--to", dest="to_month", required=True, help="YYYY-MM")
    args = parser.parse_args()

    gu_codes = [args.gu] if args.gu else list(SEOUL_GU_CODES)
    months = month_range(args.from_month, args.to_month)
    log.info("ingest_start", districts=len(gu_codes), months=len(months))

    client = MolitClient(get_settings().molit_api_key)
    session_factory = get_session_factory()

    # FX for USD normalization (run scripts/ingest_fx.py first). Missing table
    # or empty rates → prices stored KRW-only, backfillable later.
    async with session_factory() as session:
        fx = await FxProvider.load(session, "KRW")
    if len(fx) == 0:
        log.warning("fx_table_empty", hint="run scripts/ingest_fx.py for USD normalization")
        fx = None

    total = {"fetched": 0, "cancelled": 0, "parse_errors": 0, "no_fx": 0}
    try:
        for gu in gu_codes:
            for ymd in months:
                stats = await ingest_month(client, session_factory, gu, ymd, fx=fx)
                for k in total:
                    total[k] += stats[k]
                log.info("ingest_month_done", gu=gu, ymd=ymd, **stats)
                await asyncio.sleep(RATE_LIMIT_SLEEP_S)
    finally:
        await client.aclose()
    log.info("ingest_complete", **total)


if __name__ == "__main__":
    asyncio.run(main())
