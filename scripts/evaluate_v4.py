"""v4 evaluation — confidence tiers + conformal CIs on the holdout (docs/03 §3.5, §6).

Flow:
1. v3 pipeline: detrend → engineer → split → predict val + holdout (nominal)
2. Fit conformal calibrator on VALIDATION residuals (per 자치구)
3. Per holdout row: 95% CI + confidence score → tier
4. Report metrics per tier — the protocol only issues AUTO_ISSUE (+flagged REVIEW)

Usage:
    python scripts/evaluate_v4.py --model-id avm-kr-seoul-apt-v3-...
"""

import argparse
import asyncio
import json
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from packages.avm.backtest.metrics import ci_coverage, compute_metrics, median_ci_width
from packages.avm.backtest.splits import DEFAULT_SPLIT, split_transactions
from packages.avm.confidence import ConfidenceInputs, confidence_score, confidence_tier
from packages.avm.conformal import ConformalCalibrator
from packages.avm.models.v2_lightgbm import load_v2, predict_v2
from packages.avm.models.v3_time_adjust import (
    compute_group_indices,
    detrend_prices_grouped,
    region_group,
    rescale_predictions_grouped,
)
from packages.avm.registry import parse_model_id

log = structlog.get_logger()


def row_confidence(row) -> float:
    return confidence_score(
        ConfidenceInputs(
            same_complex_transactions_365d=int(row["complex_transaction_count_365d"] or 0),
            days_since_last_complex_tx=float(
                row["complex_last_transaction_days_ago"]
                if pd.notna(row["complex_last_transaction_days_ago"])
                else 999
            ),
            model_prediction_std=float(row["rel_std"]),
            segment_backtest_accuracy=float(row["seg_ppe10"]),
        )
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--models-dir", default="models/")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    info = parse_model_id(args.model_id)
    if int(info["version"]) < 3:
        raise SystemExit("v4 evaluation expects a v3+ model")

    from scripts.train_avm import engineer, load_training_frame

    df = await load_training_frame()
    df = df.assign(idx_group=region_group(df["admin_level_2"]))
    indices = compute_group_indices(df)
    df = df.assign(price_nominal=df["price"], price=detrend_prices_grouped(df, indices))
    df = engineer(df)
    _train, val, holdout = split_transactions(df, DEFAULT_SPLIT)

    model = load_v2(Path(args.models_dir) / args.model_id)

    # --- validation: fit conformal calibrator (holdout untouched) ---
    val = val.copy()
    val["prediction"] = rescale_predictions_grouped(predict_v2(model, val), val, indices)
    calibrator = ConformalCalibrator.fit(
        pred=val["prediction"],
        actual=val["price_nominal"].astype(float),
        segments=val["admin_level_2"],
    )

    # --- holdout: ADAPTIVE conformal (expanding, 1-month embargo) ---
    # Val-only calibration undercovers when the error distribution shifts
    # (observed: 84.6% vs 95% target). Production recalibrates monthly on the
    # newest residuals — MOLIT actuals arrive within ~30 days — so backtest
    # does the same: month m uses val residuals + holdout residuals ≤ m-2.
    holdout = holdout.copy()
    holdout["prediction"] = rescale_predictions_grouped(
        predict_v2(model, holdout), holdout, indices
    )
    holdout["_m"] = pd.to_datetime(holdout["transaction_date"]).dt.to_period("M")

    def resid_frame(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "prediction": d["prediction"],
                "actual": d["price_nominal"].astype(float),
                "segment": d["admin_level_2"],
                "month": pd.to_datetime(d["transaction_date"]).dt.to_period("M"),
            }
        )

    # Rolling 6-month calibration window: stale residuals dilute the newest
    # error regime (expanding window still undercovered at 87%)
    all_resid = pd.concat([resid_frame(val), resid_frame(holdout)])
    CAL_WINDOW_MONTHS = 6

    # ACI (Gibbs & Candès): adjust alpha online from realized coverage —
    # widens intervals in shifting regimes using PAST months only (no leakage)
    ACI_GAMMA = 0.05
    TARGET_MISS = 0.05
    alpha_m = 0.05

    for col in ["ci_lower", "ci_upper", "rel_std", "seg_ppe10"]:
        holdout[col] = pd.NA
    for m in sorted(holdout["_m"].unique()):
        window = all_resid[
            (all_resid["month"] <= m - 2)  # 1-month embargo
            & (all_resid["month"] >= m - 2 - CAL_WINDOW_MONTHS)
        ]
        calib = window if len(window) >= 2000 else all_resid[all_resid["month"] <= m - 2]
        cal_m = ConformalCalibrator.fit(
            calib["prediction"], calib["actual"], calib["segment"], alpha=alpha_m
        )
        rows = holdout["_m"] == m
        lo, hi = cal_m.interval(holdout.loc[rows, "prediction"], holdout.loc[rows, "admin_level_2"])
        holdout.loc[rows, "ci_lower"] = lo
        holdout.loc[rows, "ci_upper"] = hi
        holdout.loc[rows, "rel_std"] = cal_m.rel_std(holdout.loc[rows, "admin_level_2"]).values
        holdout.loc[rows, "seg_ppe10"] = cal_m.ppe10(holdout.loc[rows, "admin_level_2"]).values

        # ACI update from this month's realized miss rate (known next month)
        a = holdout.loc[rows, "price_nominal"].astype(float)
        miss = float(
            ((a < holdout.loc[rows, "ci_lower"]) | (a > holdout.loc[rows, "ci_upper"])).mean()
        )
        alpha_m = float(np.clip(alpha_m + ACI_GAMMA * (TARGET_MISS - miss), 0.005, 0.20))
    for col in ["ci_lower", "ci_upper", "rel_std", "seg_ppe10"]:
        holdout[col] = holdout[col].astype(float)
    holdout["confidence"] = holdout.apply(row_confidence, axis=1)
    holdout["tier"] = holdout["confidence"].map(confidence_tier)

    # --- tier report ---
    results = {}
    print(f"\n=== v4 tier analysis — {args.model_id} (holdout n={len(holdout):,}) ===\n")
    header = f"{'tier':<20}{'n':>8}{'share':>8}{'MdAPE':>8}{'PPE10':>8}{'CI-95':>8}{'CI-width':>10}"
    print(header)
    print("-" * len(header))

    tiers = ["AUTO_ISSUE", "REVIEW_RECOMMENDED", "REFUSE"]
    for tier in [*tiers, "__issued__", "__all__"]:
        if tier == "__all__":
            sub = holdout
        elif tier == "__issued__":
            sub = holdout[holdout["tier"] != "REFUSE"]
        else:
            sub = holdout[holdout["tier"] == tier]
        if sub.empty:
            continue
        m = compute_metrics(sub["prediction"].values, sub["price_nominal"].astype(float).values)
        cov = ci_coverage(
            sub["price_nominal"].astype(float).values,
            sub["ci_lower"].values,
            sub["ci_upper"].values,
        )
        width = median_ci_width(
            sub["prediction"].values, sub["ci_lower"].values, sub["ci_upper"].values
        )
        share = len(sub) / len(holdout)
        label = {"__issued__": "ISSUED (auto+rev)", "__all__": "ALL"}.get(tier, tier)
        print(
            f"{label:<20}{len(sub):>8,}{share:>8.1%}{m.mdape:>8.1%}{m.ppe10:>8.1%}"
            f"{cov:>8.1%}{width:>10.1%}"
        )
        results[label] = {
            "n": len(sub),
            "share": round(share, 4),
            **m.to_dict(),
            "ci_coverage_95": cov,
            "ci_width_median": width,
        }

    out_dir = Path(args.output or f"reports/v4_eval_{args.model_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tier_analysis.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out_dir / "conformal.json").write_text(
        json.dumps(calibrator.to_json(), indent=2), encoding="utf-8"
    )
    # persist calibrator alongside the model artifact for serving
    (Path(args.models_dir) / args.model_id / "conformal.json").write_text(
        json.dumps(calibrator.to_json(), indent=2), encoding="utf-8"
    )
    print(f"\nartifacts: {out_dir}")

    # headline check vs docs/04 §3.3 targets
    issued = results.get("ISSUED (auto+rev)")
    if issued:
        ok_cov = 0.93 <= issued["ci_coverage_95"] <= 0.97
        print(
            f"\nissued-subset: MdAPE {issued['mdape']:.1%} | CI-95 coverage "
            f"{issued['ci_coverage_95']:.1%} ({'target 93-97% OK' if ok_cov else 'OUT OF TARGET'})"
        )


if __name__ == "__main__":
    asyncio.run(main())
