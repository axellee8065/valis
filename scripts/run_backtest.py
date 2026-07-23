"""Run a holdout backtest for a trained model (docs/04 §6.1).

Usage:
    python scripts/run_backtest.py --model-id avm-kr-seoul-apt-v2-... \
        --output-dir reports/backtest_v2/ --include-baselines B2
"""

import argparse
import asyncio
import pickle
from pathlib import Path

import structlog

from packages.avm.backtest.baselines import baseline_b2_complex_median
from packages.avm.backtest.runner import run_backtest
from packages.avm.backtest.splits import DEFAULT_SPLIT, split_transactions
from packages.avm.registry import git_short_sha, parse_model_id

log = structlog.get_logger()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--models-dir", default="models/")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--include-baselines", default="B2", help="comma list: B1,B2,B4")
    args = parser.parse_args()

    info = parse_model_id(args.model_id)
    out_dir = Path(args.output_dir or f"reports/backtest_{args.model_id}")

    # Lazy import to avoid heavy deps when just checking CLI wiring
    from scripts.train_avm import engineer, load_training_frame

    model_dir = Path(args.models_dir) / args.model_id
    version = int(info["version"])

    df = await load_training_frame()

    # v3: detrend BEFORE feature engineering (same transform as training —
    # rolling features and target live in stationary space)
    indices = None
    if version >= 3:
        from packages.avm.models.v3_time_adjust import (
            compute_group_indices,
            detrend_prices_grouped,
            region_group,
        )

        df = df.assign(idx_group=region_group(df["admin_level_2"]))
        indices = compute_group_indices(df)
        df = df.assign(price_nominal=df["price"], price=detrend_prices_grouped(df, indices))

    df = engineer(df)
    _train, _val, holdout = split_transactions(df, DEFAULT_SPLIT)
    if holdout.empty:
        raise SystemExit("Holdout window has no transactions — ingest more data first.")
    if version == 1:
        from packages.avm.models.v1_hedonic import predict_v1

        with open(model_dir / "model.pkl", "rb") as f:
            ms = pickle.load(f)
        holdout = holdout.copy()
        holdout["prediction"] = predict_v1(ms, holdout)
    else:
        from packages.avm.models.v2_lightgbm import load_v2, predict_v2

        model = load_v2(model_dir)
        holdout = holdout.copy()
        pred = predict_v2(model, holdout)
        if version >= 3:
            # model predicts DETRENDED prices — rescale once at target month
            from packages.avm.models.v3_time_adjust import rescale_predictions_grouped

            pred = rescale_predictions_grouped(pred, holdout, indices)
        holdout["prediction"] = pred

    baselines = {}
    wanted = {b.strip().upper() for b in args.include_baselines.split(",") if b.strip()}
    if "B2" in wanted:
        past = df[df["transaction_date"] < str(DEFAULT_SPLIT.holdout_start)]
        baselines["B2_complex_median"] = baseline_b2_complex_median(holdout, past)

    # metrics are always against NOMINAL prices (v3's price col is detrended)
    actual_col = "price_nominal" if version >= 3 else "price"
    holdout["price_krw"] = holdout[actual_col].astype(float)
    result = run_backtest(
        holdout_df=holdout,
        pred_col="prediction",
        actual_col=actual_col,
        model_id=args.model_id,
        split=DEFAULT_SPLIT,
        output_dir=out_dir,
        baselines=baselines,
        code_git_sha=git_short_sha(),
    )
    print(f"backtest: {result.backtest_id}")
    print(f"MdAPE:    {result.overall.mdape:.2%}")
    print(f"PPE10:    {result.overall.ppe10:.2%}")
    print(f"Coverage: {result.overall.coverage:.2%}")
    print(f"Report:   {result.output_dir / 'report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
