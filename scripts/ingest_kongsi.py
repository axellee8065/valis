"""공동주택 공시가격 bulk ingestion (docs/02 §2.1.B) — B1 baseline data.

For every distinct parcel, fetch official prices by PNU (8 concurrent) and
match units to our property master. Match key within a parcel:
(floor, net_area×100 ± 1㎡) — the same identity our canonical local ID uses.
Ambiguous or unmatched records are counted and skipped, never guessed.
Inserts are batched (one multi-VALUES INSERT per flush) for remote-DB
throughput.

Usage:
    python scripts/ingest_kongsi.py --year 2026
    python scripts/ingest_kongsi.py --year 2025 --limit 50
"""

import argparse
import asyncio
import re
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.adapter_kr.kongsi.client import KongsiApiError, KongsiClient
from packages.adapter_kr.kongsi.normalizer import (
    KongsiRecordError,
    to_government_valuation,
)
from packages.core.config import get_settings
from packages.core.db.models import GovernmentValuationRow
from packages.core.db.session import get_session_factory
from packages.core.fx import FxProvider

log = structlog.get_logger()

RATE_SLEEP_S = 0.1
CONCURRENCY = 2  # VWorld throttles aggressive concurrency (429 → 60s stalls)
CHUNK = 100
FLUSH_AT = 500
AREA_TOLERANCE_X100 = 100  # ±1.00㎡


def floor_from_ho(ho_nm: str) -> int | None:
    """'1201' → 12, '201호' → 2, 'B101' → None (지하 제외)."""
    if str(ho_nm or "").upper().startswith("B"):
        return None
    txt = re.sub(r"[^0-9]", "", str(ho_nm or ""))
    if len(txt) >= 3:
        return int(txt[:-2]) or None
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    client = KongsiClient(settings.kongsi_api_key, api_domain=settings.kongsi_api_domain)
    session_factory = get_session_factory()

    async with session_factory() as session:
        fx_provider = await FxProvider.load(session, "KRW")
        fx = fx_provider.rate_at(f"{args.year}-01-01") or Decimal("0.0007")
        rows = await session.execute(
            text("""SELECT split_part(local_id_canonical, '-', 2) AS sgg,
                           split_part(local_id_canonical, '-', 3) AS umd,
                           split_part(local_id_canonical, '-', 4) AS land,
                           split_part(local_id_canonical, '-', 5) AS bon,
                           split_part(local_id_canonical, '-', 6) AS bu,
                           array_agg(global_id) AS gids,
                           array_agg(floor_number) AS floors,
                           array_agg((net_area_sqm * 100)::int) AS areas
                    FROM properties WHERE country_code = 'KR'
                    GROUP BY 1, 2, 3, 4, 5""")
        )
        parcels = rows.all()
    if args.limit:
        parcels = parcels[: args.limit]
    log.info("kongsi_bulk_start", parcels=len(parcels), year=args.year, fx=float(fx))

    matched = unmatched = api_errors = dead = 0
    now = datetime.now(UTC)
    pending: list[dict] = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async def flush(session) -> None:
        nonlocal pending
        if not pending:
            return
        # dedupe within batch — ON CONFLICT cannot touch the same row twice
        unique = {(r["global_id"], r["valuation_type"], r["assessment_year"]): r for r in pending}
        stmt = (
            pg_insert(GovernmentValuationRow)
            .values(list(unique.values()))
            .on_conflict_do_nothing(constraint="uq_gov_val")
        )
        await session.execute(stmt)
        await session.commit()
        pending = []

    async def fetch_one(p):
        pnu = f"{p.sgg}{p.umd}{p.land}{p.bon}{p.bu}"
        async with sem:
            try:
                records = await client.fetch_by_pnu(pnu, args.year)
            except (KongsiApiError, Exception) as exc:
                return p, None, str(exc)[:120]
            await asyncio.sleep(RATE_SLEEP_S)
            return p, records, None

    def match_records(p, records) -> None:
        nonlocal matched, unmatched, dead
        unit_map: dict[tuple[int, int], list[str]] = {}
        for gid, fl, ar in zip(p.gids, p.floors, p.areas, strict=True):
            if fl is not None and ar is not None:
                unit_map.setdefault((int(fl), int(ar)), []).append(gid)

        for raw in records:
            fl = floor_from_ho(raw.get("hoNm"))
            try:
                area = round(float(raw.get("prvuseAr") or 0) * 100)
            except ValueError:
                area = 0
            if not fl or not area:
                unmatched += 1
                continue
            hits = [
                gids
                for (ufl, uar), gids in unit_map.items()
                if ufl == fl and abs(uar - area) <= AREA_TOLERANCE_X100
            ]
            flat = [g for gs in hits for g in gs]
            if len(flat) != 1:
                unmatched += 1  # ambiguous or unknown unit — never guess
                continue
            try:
                gv = to_government_valuation(raw, flat[0], fx_krw_usd=fx, ingested_at=now)
            except KongsiRecordError:
                dead += 1
                continue
            pending.append(gv.model_dump())
            matched += 1

    try:
        async with session_factory() as session:
            for start in range(0, len(parcels), CHUNK):
                chunk = parcels[start : start + CHUNK]
                results = await asyncio.gather(*(fetch_one(p) for p in chunk))
                for p, records, err in results:
                    if err is not None:
                        api_errors += 1
                        if api_errors <= 5:
                            log.warning("kongsi_fetch_failed", bon=p.bon, error=err)
                        continue
                    match_records(p, records)
                    if len(pending) >= FLUSH_AT:
                        await flush(session)
                await flush(session)
                log.info(
                    "kongsi_progress",
                    done=min(start + CHUNK, len(parcels)),
                    matched=matched,
                    unmatched=unmatched,
                    errors=api_errors,
                )
    finally:
        await client.aclose()
    log.info("kongsi_bulk_done", matched=matched, unmatched=unmatched, errors=api_errors, dead=dead)


if __name__ == "__main__":
    asyncio.run(main())
