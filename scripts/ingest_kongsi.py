"""공동주택 공시가격 bulk ingestion (docs/02 §2.1.B) — B1 baseline data.

For every distinct parcel, fetch official prices by PNU and match units to our
property master. Match key within a parcel: (floor, net_area×100) — the same
identity our canonical local ID uses. Ambiguous or unmatched records are
counted and skipped (never guessed).

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

RATE_SLEEP_S = 0.1  # ~10 req/s courtesy


def floor_from_ho(ho_nm: str) -> int | None:
    """'1201' → 12, '201호' → 2, 'B101' → None (지하 제외)."""
    txt = re.sub(r"[^0-9]", "", str(ho_nm or ""))
    if str(ho_nm or "").upper().startswith("B"):
        return None
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

    matched, unmatched, api_errors, dead = 0, 0, 0, 0
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            for i, p in enumerate(parcels, 1):
                pnu = f"{p.sgg}{p.umd}{p.land}{p.bon}{p.bu}"
                try:
                    records = await client.fetch_by_pnu(pnu, args.year)
                except (KongsiApiError, Exception) as exc:
                    api_errors += 1
                    if api_errors <= 5:
                        log.warning("kongsi_fetch_failed", pnu=pnu, error=str(exc)[:120])
                    await asyncio.sleep(RATE_SLEEP_S)
                    continue

                # unit lookup within parcel: (floor, area_x100 ±100) → global_id
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
                    candidates = [
                        gids
                        for (ufl, uar), gids in unit_map.items()
                        if ufl == fl and abs(uar - area) <= 100
                    ]
                    flat = [g for gs in candidates for g in gs]
                    if len(flat) != 1:
                        unmatched += 1  # ambiguous or unknown unit — never guess
                        continue
                    try:
                        gv = to_government_valuation(raw, flat[0], fx_krw_usd=fx, ingested_at=now)
                    except KongsiRecordError:
                        dead += 1
                        continue
                    stmt = (
                        pg_insert(GovernmentValuationRow)
                        .values(**gv.model_dump())
                        .on_conflict_do_nothing(constraint="uq_gov_val")
                    )
                    await session.execute(stmt)
                    matched += 1

                if i % 200 == 0:
                    await session.commit()
                    log.info(
                        "kongsi_progress",
                        done=i,
                        matched=matched,
                        unmatched=unmatched,
                        errors=api_errors,
                    )
                await asyncio.sleep(RATE_SLEEP_S)
            await session.commit()
    finally:
        await client.aclose()
    log.info("kongsi_bulk_done", matched=matched, unmatched=unmatched, errors=api_errors, dead=dead)


if __name__ == "__main__":
    asyncio.run(main())
