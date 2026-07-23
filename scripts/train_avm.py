"""Train an AVM model version (docs/03 §4).

Usage:
    python scripts/train_avm.py --model v2 --output models/
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import select

from packages.avm.backtest.splits import DEFAULT_SPLIT, split_transactions
from packages.avm.features.common import (
    add_complex_rolling_features,
    add_intrinsic_features,
)
from packages.avm.registry import git_short_sha, make_model_id
from packages.core.db.models import PropertyRow, TransactionRow
from packages.core.db.session import get_session_factory

log = structlog.get_logger()


async def load_training_frame() -> pd.DataFrame:
    """Join transactions with property attributes into a modeling frame.
    Excludes cancelled and related-party transactions (docs/02 §5.4)."""
    async with get_session_factory()() as session:
        stmt = (
            select(
                TransactionRow.global_id,
                TransactionRow.transaction_date,
                TransactionRow.price_original_amount.label("price"),
                PropertyRow.net_area_sqm,
                PropertyRow.floor_number,
                PropertyRow.floors_total,
                PropertyRow.built_year,
                PropertyRow.units_in_building,
                PropertyRow.admin_level_2,
                PropertyRow.admin_level_3,
                PropertyRow.heating_type,
                PropertyRow.complex_id,
            )
            .join(PropertyRow, PropertyRow.global_id == TransactionRow.global_id)
            .where(
                TransactionRow.is_cancelled.is_(False),
                TransactionRow.is_related_party.is_(False),
                TransactionRow.transaction_type == "SALE",
            )
        )
        rows = (await session.execute(stmt)).all()
    df = pd.DataFrame(
        rows,
        columns=[
            "global_id",
            "transaction_date",
            "price",
            "net_area_sqm",
            "floor_number",
            "floors_total",
            "built_year",
            "units_in_building",
            "admin_level_2",
            "admin_level_3",
            "heating_type",
            "complex_id",
        ],
    )
    log.info("training_frame_loaded", rows=len(df))
    return df


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    df = add_intrinsic_features(df)
    df = add_complex_rolling_features(df)
    return df


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["v1", "v2", "v3"], required=True)
    parser.add_argument("--output", default="models/")
    args = parser.parse_args()

    df = await load_training_frame()

    # v3: detrend prices BEFORE feature engineering so rolling comparable
    # features live in the same stationary space as the target. Rescaling by
    # the index happens once, at prediction time — never double-counted.
    indices = None
    if args.model == "v3":
        from packages.avm.models.v3_time_adjust import (
            compute_group_indices,
            detrend_prices_grouped,
            region_group,
        )

        log.info("computing_repeat_sales_index", groups="gangnam3/other")
        df = df.assign(idx_group=region_group(df["admin_level_2"]))
        indices = compute_group_indices(df)
        df = df.assign(price_nominal=df["price"], price=detrend_prices_grouped(df, indices))

    df = engineer(df)
    train, val, holdout = split_transactions(df, DEFAULT_SPLIT)
    log.info("split", train=len(train), val=len(val), holdout=len(holdout))

    version = int(args.model[1:])
    model_id = make_model_id("kr", "seoul", "apt", version)
    out_dir = Path(args.output) / model_id

    manifest = {
        "model_id": model_id,
        "trained_at": datetime.now(UTC).isoformat(),
        "git_sha": git_short_sha(),
        "train_range": [str(train["transaction_date"].min()), str(train["transaction_date"].max())],
        "train_rows": len(train),
        "val_rows": len(val),
        "random_state": 42,
        "versions": {"pandas": pd.__version__},
    }

    if args.model == "v1":
        import pickle

        from packages.avm.models.v1_hedonic import predict_v1, train_v1

        ms = train_v1(train)
        val_pred = predict_v1(ms, val)
        from packages.avm.backtest.metrics import compute_metrics

        metrics = compute_metrics(val_pred.values, val["price"].astype(float).values)
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "model.pkl", "wb") as f:
            pickle.dump(ms, f)
        (out_dir / "metrics.json").write_text(json.dumps(metrics.to_dict(), indent=2))
    elif args.model == "v2":
        from packages.avm.backtest.metrics import compute_metrics
        from packages.avm.models.v2_lightgbm import predict_v2, save_v2, train_v2

        model = train_v2(train, val)
        val_pred = predict_v2(model, val)
        metrics = compute_metrics(val_pred.values, val["price"].astype(float).values)
        save_v2(model, out_dir, metrics.to_dict(), manifest)
    else:  # v3 = v2 + repeat-sales time adjustment (docs/03 §3.4)
        from packages.avm.backtest.metrics import compute_metrics
        from packages.avm.models.v2_lightgbm import predict_v2, save_v2, train_v2
        from packages.avm.models.v3_time_adjust import rescale_predictions_grouped

        # df["price"] (and all rolling features) are already detrended above
        model = train_v2(train, val)
        val_pred = rescale_predictions_grouped(predict_v2(model, val), val, indices)
        metrics = compute_metrics(val_pred.values, val["price_nominal"].astype(float).values)
        save_v2(model, out_dir, metrics.to_dict(), manifest)
        (out_dir / "index.json").write_text(
            json.dumps({k: v.to_json() for k, v in indices.items()}, indent=1)
        )

    (out_dir / "training_data_manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("training_done", model_id=model_id, val_mdape=metrics.mdape)
    print(f"model_id: {model_id}")
    print(f"validation MdAPE: {metrics.mdape:.2%}  PPE10: {metrics.ppe10:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
