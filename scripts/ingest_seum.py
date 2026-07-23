"""세움터 건축물대장 bulk enrichment (docs/02 §2.1.C).

For every distinct parcel in the property master, fetch 표제부 and fill the
fields MOLIT trades lack: units_in_building, floors_total, building_area_sqm,
parking_spaces (+ built_year fallback). Only NULL columns are filled
(COALESCE semantics) — never overwrites trade-derived data.

Parcel = first 5 components of local_id_canonical:
    KR-{sgg5}-{umd5}-{land1}-{bonbun4}-{bubun4}-...

Usage:
    python scripts/ingest_seum.py            # all parcels
    python scripts/ingest_seum.py --limit 50 # trial
"""

import argparse
import asyncio

import structlog
from sqlalchemy import text

from packages.adapter_kr.seum.client import RATE_LIMIT_SLEEP_S, SeumApiError, SeumClient
from packages.adapter_kr.seum.normalizer import is_apartment, to_property_enrichment
from packages.core.config import get_settings
from packages.core.db.session import get_session_factory

log = structlog.get_logger()


def parcel_of(canonical: str) -> tuple[str, str, str, str, str] | None:
    parts = canonical.split("-")
    if len(parts) < 6 or parts[0] != "KR":
        return None
    return parts[1], parts[2], parts[3], parts[4], parts[5]  # sgg, umd, land, bon, bu


SMALLINT_MAX = 32_767  # DB column bounds — clamp register anomalies


def aggregate(records: list[dict]) -> dict:
    """Parcel-level rollup over apartment buildings.

    총괄표제부 (regstrKindCd=1, complex-wide record) is preferred when present;
    otherwise per-동 표제부 (kind=3) are summed. Some registers repeat
    complex-wide parking on every 동 — values are clamped to column bounds.
    """
    apt_records = [r for r in records if is_apartment(r)]
    if not apt_records:
        return {}
    master = [r for r in apt_records if str(r.get("regstrKindCd", "")).strip() == "1"]
    use = master if master else apt_records
    combine_units = sum if not master else max
    apt = [to_property_enrichment(r) for r in use]

    agg: dict = {}
    units = [e["units_in_building"] for e in apt if "units_in_building" in e]
    floors = [e["floors_total"] for e in apt if "floors_total" in e]
    areas = [e["building_area_sqm"] for e in apt if "building_area_sqm" in e]
    built = [e["built_year"] for e in apt if "built_year" in e]
    parking = [e["parking_spaces"] for e in apt if "parking_spaces" in e]
    if units:
        agg["units_in_building"] = combine_units(units)  # 단지 세대수 (대단지 피처)
    if floors:
        agg["floors_total"] = min(max(floors), SMALLINT_MAX)
    if areas:
        agg["building_area_sqm"] = round(sum(areas), 2)
    if built:
        agg["built_year"] = min(built)
    if parking:
        agg["parking_spaces"] = min(max(parking) if master else sum(parking), SMALLINT_MAX)
    return agg


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    client = SeumClient(get_settings().seum_api_key)
    session_factory = get_session_factory()

    async with session_factory() as session:
        rows = await session.execute(
            text("""SELECT DISTINCT split_part(local_id_canonical, '-', 2) AS sgg,
                           split_part(local_id_canonical, '-', 3) AS umd,
                           split_part(local_id_canonical, '-', 4) AS land,
                           split_part(local_id_canonical, '-', 5) AS bon,
                           split_part(local_id_canonical, '-', 6) AS bu
                    FROM properties WHERE country_code = 'KR'
                      AND units_in_building IS NULL""")
        )
        parcels = rows.all()
    if args.limit:
        parcels = parcels[: args.limit]
    log.info("seum_bulk_start", parcels=len(parcels))

    enriched, empty, errors = 0, 0, 0
    sem = asyncio.Semaphore(10)  # 10 concurrent — well under the 30/s quota

    async def fetch_one(parcel):
        sgg, umd, land, bon, bu = parcel
        async with sem:
            try:
                records = await client.fetch_title_info(
                    sgg_cd=sgg,
                    umd_cd=umd,
                    bun=bon,
                    ji=bu,
                    # MOLIT landCd 1=대지, 2=산 → 세움터 platGbCd 0=대지, 1=산
                    plat_gb_cd={"1": "0", "2": "1"}.get(land, "0"),
                )
            except (SeumApiError, Exception) as exc:
                return parcel, None, str(exc)[:120]
            await asyncio.sleep(RATE_LIMIT_SLEEP_S)
            return parcel, aggregate(records), None

    CHUNK = 200
    try:
        async with session_factory() as session:
            for start in range(0, len(parcels), CHUNK):
                chunk = parcels[start : start + CHUNK]
                results = await asyncio.gather(*(fetch_one(p) for p in chunk))
                for (sgg, umd, land, bon, bu), agg, err in results:
                    if err is not None:
                        errors += 1
                        if errors <= 5:
                            log.warning(
                                "seum_fetch_failed", parcel=f"{sgg}-{umd}-{bon}-{bu}", error=err
                            )
                        continue
                    if not agg:
                        empty += 1
                        continue
                    sets = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in agg)
                    try:
                        await session.execute(
                            text(
                                f"""UPDATE properties SET {sets}, updated_at = NOW()
                                    WHERE local_id_canonical LIKE :prefix"""
                            ),
                            {**agg, "prefix": f"KR-{sgg}-{umd}-{land}-{bon}-{bu}-%"},
                        )
                        enriched += 1
                    except Exception as exc:
                        # one bad parcel must not poison the whole chunk
                        await session.rollback()
                        errors += 1
                        log.warning(
                            "seum_update_failed",
                            parcel=f"{sgg}-{umd}-{bon}-{bu}",
                            agg=agg,
                            error=str(exc)[:120],
                        )
                await session.commit()
                log.info(
                    "seum_progress",
                    done=min(start + CHUNK, len(parcels)),
                    enriched=enriched,
                    empty=empty,
                    errors=errors,
                )
    finally:
        await client.aclose()
    log.info("seum_bulk_done", enriched=enriched, empty=empty, errors=errors)


if __name__ == "__main__":
    asyncio.run(main())
