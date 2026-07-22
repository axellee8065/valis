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


BATCH_SIZE = 500  # rows per INSERT — keeps remote-DB round trips low


async def ingest_month(
    client: MolitClient, session_factory, gu_code: str, ymd: str, fx: FxProvider | None = None
) -> dict:
    """Fetch one district+month and upsert in batches.

    Row-by-row upserts are ~2 round trips per record — unusable against a
    remote DB (Railway proxy RTT × 400k records). Batched multi-VALUES
    upserts cut it to ~4 statements per month.
    """
    stats = {"fetched": 0, "cancelled": 0, "parse_errors": 0, "no_fx": 0}
    props: dict[str, dict] = {}  # global_id → row (deduped within batch)
    txs: dict[str, dict] = {}  # source_record_id → row (last wins)

    try:
        async for raw in client.fetch_apt_trades(gu_code, ymd):
            now = datetime.now(UTC)
            deal_date = f"{raw.deal_year}-{int(raw.deal_month):02d}-{int(raw.deal_day):02d}"
            fx_rate = fx.rate_at(deal_date) if fx else None
            if fx and fx_rate is None:
                stats["no_fx"] += 1
            tx = to_transaction(raw, fx_krw_usd=fx_rate, ingested_at=now)
            prop = to_property(raw, ingested_at=now)

            props[prop.global_id] = prop.model_dump(mode="json")
            txs[tx.source_record_id] = tx.model_dump(mode="json")
            stats["fetched"] += 1
            stats["cancelled"] += int(tx.is_cancelled)
    except MolitParseError as exc:
        stats["parse_errors"] += 1
        log.error("molit_parse_error", gu=gu_code, ymd=ymd, error=str(exc))

    if not txs:
        return stats

    def chunks(rows: list[dict], size: int = BATCH_SIZE):
        for i in range(0, len(rows), size):
            yield rows[i : i + size]

    async with session_factory() as session:
        for chunk in chunks(list(props.values())):
            stmt = pg_insert(PropertyRow).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["global_id"],
                set_={
                    "updated_at": stmt.excluded.updated_at,
                    "data_sources": stmt.excluded.data_sources,
                },
            )
            await session.execute(stmt)

        for chunk in chunks(list(txs.values())):
            stmt = pg_insert(TransactionRow).values(chunk)
            # Re-reported records: latest wins on cancellation flags
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_record_id"],
                set_={
                    "is_cancelled": stmt.excluded.is_cancelled,
                    "cancelled_at": stmt.excluded.cancelled_at,
                    "registration_date": stmt.excluded.registration_date,
                    "ingested_at": stmt.excluded.ingested_at,
                },
            )
            await session.execute(stmt)
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
