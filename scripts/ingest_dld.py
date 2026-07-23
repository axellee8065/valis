"""Bulk DLD (Dubai) ingestion from the open-data mirror parquet.

Usage:
    python scripts/ingest_dld.py --parquet data/raw/ae/dld_transactions_mirror.parquet
    python scripts/ingest_dld.py --parquet ... --from 2018-01   # date floor

Scope (demo): residential unit sales only (Flat), sane-price filtered.
Off-plan pre-registrations are stored with Property.is_offplan=true and
excluded at analysis time (docs/06 §9). Idempotent via
(source, source_record_id) — identical class+date+amount rows collapse
(open data has no transaction id; documented in docs/08).
"""

import argparse
import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.adapter_ae.dld.normalizer import (
    PROCEDURE_MAP,
    RawDldTransaction,
    to_property,
    to_transaction,
)
from packages.core.db.models import PropertyRow, TransactionRow
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

BATCH_SIZE = 500
# sanity bounds (AED, sqft) — open data has degenerate rows (min price = 1 AED)
MIN_PRICE_AED = 100_000
MAX_PRICE_AED = 60_000_000
MIN_BUA_SQFT = 200
MAX_BUA_SQFT = 30_000


def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def load_mirror(path: str, from_month: str | None) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[
        df["procedure_name"].isin(PROCEDURE_MAP)
        & (df["property_type"] == "Unit")
        & (df["property_usage"].str.strip() == "Residential")
        & (df["property_sub_type"] == "Flat")
        & df["building_name"].notna()
        & df["selling_price"].between(MIN_PRICE_AED, MAX_PRICE_AED)
        & df["built_up_area_(sqft)"].between(MIN_BUA_SQFT, MAX_BUA_SQFT)
    ].copy()
    df["dt"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df = df[df["dt"].notna()]
    if from_month:
        df = df[df["dt"] >= pd.Timestamp(f"{from_month}-01")]
    return df


def to_raw(row: pd.Series) -> RawDldTransaction:
    return RawDldTransaction(
        procedure_name=_clean(row["procedure_name"]),
        instance_date=_clean(row["date"]),
        property_type=_clean(row["property_type"]),
        property_sub_type=_clean(row["property_sub_type"]),
        property_usage=_clean(row["property_usage"]),
        area_name=_clean(row["area_name"]),
        building_name=_clean(row["building_name"]),
        master_project=_clean(row["master_project"]),
        bedrooms=_clean(row["bedrooms"]),
        parkings=_clean(row["parkings"]),
        built_up_area_sqft=_clean(row["built_up_area_(sqft)"]),
        selling_price_aed=_clean(row["selling_price"]),
        raw={
            "procedure_name": _clean(row["procedure_name"]),
            "date": _clean(row["date"]),
            "area_name": _clean(row["area_name"]),
            "building_name": _clean(row["building_name"]),
            "master_project": _clean(row["master_project"]),
            "bedrooms": _clean(row["bedrooms"]),
            "built_up_area_sqft": _clean(row["built_up_area_(sqft)"]),
            "selling_price": _clean(row["selling_price"]),
            "nearest_metro": _clean(row.get("nearest_metro")),
            "nearest_mall": _clean(row.get("nearest_mall")),
        },
    )


async def ingest(df: pd.DataFrame) -> dict:
    session_factory = get_session_factory()
    stats = {"rows": 0, "offplan": 0, "skipped": 0}
    props: dict[str, dict] = {}
    txs: dict[str, dict] = {}
    now = datetime.now(UTC)

    for _, row in df.iterrows():
        try:
            raw = to_raw(row)
            tx = to_transaction(raw, ingested_at=now)
            prop = to_property(raw, ingested_at=now)
        except Exception:  # degenerate row — count, never abort the batch
            stats["skipped"] += 1
            continue
        prop_row = prop.model_dump()
        prop_row["data_sources"] = prop.model_dump(mode="json")["data_sources"]
        props[prop.global_id] = prop_row
        txs[tx.source_record_id] = tx.model_dump()
        stats["rows"] += 1
        stats["offplan"] += int(prop.is_offplan)

    log.info("normalized", **stats, unique_props=len(props), unique_txs=len(txs))

    def chunks(rows: list[dict], size: int = BATCH_SIZE):
        for i in range(0, len(rows), size):
            yield rows[i : i + size]

    async with session_factory() as session:
        done = 0
        for chunk in chunks(list(props.values())):
            stmt = pg_insert(PropertyRow).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["global_id"],
                set_={
                    "updated_at": stmt.excluded.updated_at,
                    "data_sources": stmt.excluded.data_sources,
                    "is_offplan": stmt.excluded.is_offplan,
                },
            )
            await session.execute(stmt)
            done += len(chunk)
            if done % 25_000 < BATCH_SIZE:
                log.info("props_progress", done=done)
        await session.commit()

        done = 0
        for chunk in chunks(list(txs.values())):
            stmt = pg_insert(TransactionRow).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_record_id"],
                set_={"ingested_at": stmt.excluded.ingested_at},
            )
            await session.execute(stmt)
            done += len(chunk)
            if done % 25_000 < BATCH_SIZE:
                log.info("txs_progress", done=done)
        await session.commit()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest DLD Dubai transactions")
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--from", dest="from_month", default=None, help="YYYY-MM floor")
    args = parser.parse_args()

    df = load_mirror(args.parquet, args.from_month)
    log.info("mirror_loaded", rows=len(df), from_=str(df["dt"].min()), to=str(df["dt"].max()))
    stats = await ingest(df)
    log.info("ingest_complete", **stats)


if __name__ == "__main__":
    asyncio.run(main())
