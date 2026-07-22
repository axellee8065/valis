"""Seed Seoul POIs — subway stations from 서울시 열린데이터광장 (docs/02 §2.2.E).

Usage: python scripts/seed_seoul_pois.py
Requires SEOUL_OPEN_DATA_KEY in .env.
"""

import asyncio
from decimal import Decimal

import httpx
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.core.config import get_settings
from packages.core.db.models import PointOfInterestRow
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

# 서울시 역사마스터 정보 — 784 stations with coordinates (verified live 2026-07)
# Fields: BLDN_ID, BLDN_NM (역명), ROUTE (노선), LAT, LOT
SUBWAY_URL = "http://openapi.seoul.go.kr:8088/{key}/json/subwayStationMaster/1/1000/"


async def fetch_subway_stations(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(SUBWAY_URL.format(key=api_key))
        resp.raise_for_status()
        data = resp.json()
    # Response shape: {"subwayStationMaster": {"RESULT": {...}, "row": [...]}}
    outer = next(iter(data.values()))
    result = outer.get("RESULT", {})
    if result.get("CODE") not in {None, "INFO-000"}:
        raise RuntimeError(f"Seoul API error {result.get('CODE')}: {result.get('MESSAGE')}")
    return outer.get("row", [])


async def main() -> None:
    settings = get_settings()
    if not settings.seoul_open_data_key:
        raise SystemExit("SEOUL_OPEN_DATA_KEY not set in .env")

    rows = await fetch_subway_stations(settings.seoul_open_data_key)
    log.info("subway_stations_fetched", count=len(rows))

    inserted = 0
    async with get_session_factory()() as session:
        for r in rows:
            name = r.get("BLDN_NM") or ""
            lat = r.get("LAT")
            lng = r.get("LOT")
            if not (name and lat and lng):
                continue
            stmt = (
                pg_insert(PointOfInterestRow)
                .values(
                    country_code="KR",
                    poi_type="SUBWAY_STATION",
                    name_normalized=name,
                    name_original=name,
                    latitude=Decimal(str(lat)),
                    longitude=Decimal(str(lng)),
                    metadata={"line": r.get("ROUTE"), "station_id": r.get("BLDN_ID")},
                )
                .on_conflict_do_nothing()
            )
            await session.execute(stmt)
            inserted += 1
        await session.commit()
    log.info("pois_seeded", inserted=inserted)


if __name__ == "__main__":
    asyncio.run(main())
