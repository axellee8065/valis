"""Dubai apartment AVM v1 (demo-grade, docs/08).

Pipeline (leakage-safe, v3 lessons applied):
  1. City-wide monthly median-ppsqm index; each transaction is detrended by the
     index of the PREVIOUS month (available at valuation time — no same-month
     leakage). Detrend BEFORE feature engineering (v3 lesson: detrending only
     the target double-counts market level via nominal encodings).
  2. Train-window-only target encodings for area / building.
  3. LightGBM on the detrended log price; temporal split
     train ≤ 2023-06 / val 2023-07..12 / holdout 2024-01..08 (mirror end).
  4. Conformal 95% CIs from validation residuals (per-area segments).
  5. Attestation candidates: latest holdout tx per unit class + confidence.

Usage:
    set PYTHONPATH=. && python scripts/train_avm_ae.py
"""

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text

from packages.avm.confidence import ConfidenceInputs, confidence_score
from packages.avm.conformal import ConformalCalibrator
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

TRAIN_END = "2023-06-30"
VAL_END = "2023-12-31"
DATA_END = pd.Timestamp("2024-08-22")  # mirror snapshot end — value vintage
MIN_COMPS = 5  # comp track: minimum same-class sales in the trailing 730d

BR_ORDINAL = {
    "0BR": 0.0,
    "SR": 0.5,
    "1BR": 1.0,
    "2BR": 2.0,
    "3BR": 3.0,
    "4BR": 4.0,
    "5BR": 5.0,
    "6BR": 6.0,
    "7BR": 7.0,
    "10BR": 10.0,
    "PH": 5.0,
}
FEATURES = ["log_bua", "br_ord", "area_te", "building_te", "parking"]

QUERY = """
SELECT t.global_id, t.transaction_date, t.price_usd_cents,
       p.local_id_canonical, p.admin_level_2, p.complex_id, p.complex_name,
       p.net_area_sqm, p.parking_spaces, p.community_name
FROM transactions t
JOIN properties p ON p.global_id = t.global_id
WHERE p.country_code = 'AE'
  AND t.source = 'DLD_OPEN_TRANSACTIONS'
  AND t.transaction_type = 'SALE'
  AND t.raw_payload->>'procedure_name' IN ('Sell', 'Delayed Sell')
  AND t.price_usd_cents IS NOT NULL
"""


def model_id() -> str:
    sha = (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        or "nogit"
    )
    return f"avm-ae-dubai-apt-v1-{datetime.now(UTC):%Y%m%d}-{sha}"


async def load() -> pd.DataFrame:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (await session.execute(text(QUERY))).mappings().all()
    df = pd.DataFrame([dict(r) for r in rows])
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["price"] = df["price_usd_cents"].astype(float) / 100
    df["net_area_sqm"] = df["net_area_sqm"].astype(float)
    df["ppsqm"] = df["price"] / df["net_area_sqm"]
    df["month"] = df["transaction_date"].dt.to_period("M")
    df["br_code"] = df["local_id_canonical"].str.split("-").str[-2]
    return df


def add_index(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Monthly city index (3-month rolling median of monthly median ppsqm),
    applied with a 1-month lag: valuing in month m uses index through m-1."""
    monthly = df.groupby("month")["ppsqm"].median().sort_index()
    idx = monthly.rolling(3, min_periods=1).median()
    lagged = idx.shift(1)
    df["idx_lag"] = df["month"].map(lagged)
    df = df[df["idx_lag"].notna()].copy()
    df["y"] = np.log(df["price"]) - np.log(df["idx_lag"])
    return df, idx


def encode(train: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Train-window-only target encodings on the DETRENDED target."""
    area_te = train.groupby("admin_level_2")["y"].median()
    bld_te = train.groupby("complex_id")["y"].median()
    df["area_te"] = df["admin_level_2"].map(area_te)
    df["building_te"] = df["complex_id"].map(bld_te).fillna(df["area_te"])
    df["log_bua"] = np.log(df["net_area_sqm"])
    df["br_ord"] = df["br_code"].map(BR_ORDINAL)
    df["parking"] = df["parking_spaces"].astype(float)
    return df


def mdape(pred: pd.Series, actual: pd.Series) -> float:
    return float(((pred - actual).abs() / actual).median())


def ppe10(pred: pd.Series, actual: pd.Series) -> float:
    return float((((pred - actual).abs() / actual) <= 0.10).mean())


async def main() -> None:
    mid = model_id()
    df = await load()
    log.info(
        "loaded",
        rows=len(df),
        classes=df["global_id"].nunique(),
        span=f"{df['transaction_date'].min():%Y-%m}..{df['transaction_date'].max():%Y-%m}",
    )

    df, idx = add_index(df)
    train = df[df["transaction_date"] <= TRAIN_END]
    val = df[(df["transaction_date"] > TRAIN_END) & (df["transaction_date"] <= VAL_END)]
    hold = df[df["transaction_date"] > VAL_END]
    log.info("split", train=len(train), val=len(val), holdout=len(hold))

    df = encode(train, df)
    train, val, hold = (df.loc[s.index] for s in (train, val, hold))

    booster = lgb.train(
        {
            "objective": "regression",
            "metric": "l2",
            "learning_rate": 0.05,
            "num_leaves": 63,
            "min_data_in_leaf": 40,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbosity": -1,
            "seed": 7,
        },
        lgb.Dataset(train[FEATURES], train["y"]),
        num_boost_round=2000,
        valid_sets=[lgb.Dataset(val[FEATURES], val["y"])],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )

    for name, part in (("val", val), ("holdout", hold)):
        pred = np.exp(booster.predict(part[FEATURES]) + np.log(part["idx_lag"]))
        part = part.assign(prediction=pred)
        m, p = mdape(part["prediction"], part["price"]), ppe10(part["prediction"], part["price"])
        log.info(f"{name}_hedonic_metrics", mdape=round(m, 4), ppe10=round(p, 4))

    # ── comp track (primary for attestation): same-class trailing median ──
    # Liquid, tight unit classes are where an AVM is honestly accurate here
    # (holdout: n≥5 & comp_std≤0.04 → MdAPE 5.1%, PPE10 76%). The hedonic
    # stays as the illiquid fallback and is NOT attested in the demo.
    def comp_stats(part: pd.DataFrame) -> pd.DataFrame:
        grouped = {k: g for k, g in df.groupby("global_id")}
        rows = []
        for r in part.itertuples():
            g = grouped[r.global_id]
            prior = g[
                (g["transaction_date"] < r.transaction_date - pd.Timedelta(days=1))
                & (g["transaction_date"] >= r.transaction_date - pd.Timedelta(days=730))
            ]
            if len(prior) < MIN_COMPS:
                continue
            rows.append(
                {
                    "index": r.Index,
                    "n_comps": len(prior),
                    "comp_std": float(prior["y"].std()),
                    "comp_pred": float(np.exp(prior["y"].median() + np.log(r.idx_lag))),
                }
            )
        out = pd.DataFrame(rows).set_index("index")
        return part.join(out, how="inner")

    def bucket(std: float) -> str:
        if std <= 0.04:
            return "T04"
        if std <= 0.06:
            return "T06"
        if std <= 0.08:
            return "T08"
        return "LOOSE"

    val_c = comp_stats(val)
    hold_c = comp_stats(hold)
    val_c["segment"] = val_c["comp_std"].map(bucket)
    hold_c["segment"] = hold_c["comp_std"].map(bucket)
    cal = ConformalCalibrator.fit(val_c["comp_pred"], val_c["price"], val_c["segment"])

    for seg_name, sub in hold_c.groupby("segment"):
        log.info(
            "holdout_comp_metrics",
            segment=seg_name,
            rows=len(sub),
            mdape=round(mdape(sub["comp_pred"], sub["price"]), 4),
            ppe10=round(ppe10(sub["comp_pred"], sub["price"]), 4),
        )
    lo, hi = cal.interval(hold_c["comp_pred"], hold_c["segment"])
    cover = float(((hold_c["price"] >= lo) & (hold_c["price"] <= hi)).mean())
    log.info("holdout_comp_ci_coverage", coverage=round(cover, 4))

    # --- attestation candidates: class state as of DATA_END (comp track) ---
    stats_end = df["transaction_date"].max()
    recent = df[df["transaction_date"] >= stats_end - pd.Timedelta(days=730)]
    agg = recent.groupby("global_id").agg(
        n_comps=("y", "count"),
        comp_std=("y", "std"),
        comp_med=("y", "median"),
        n365=("transaction_date", lambda s: int((s >= stats_end - pd.Timedelta(days=365)).sum())),
        last_tx=("transaction_date", "max"),
    )
    agg = agg[agg["n_comps"] >= MIN_COMPS]
    last = (
        df.sort_values("transaction_date")
        .drop_duplicates("global_id", keep="last")
        .set_index("global_id")
        .join(agg, how="inner")
        .reset_index()
    )
    last["value_now"] = np.exp(last["comp_med"] + np.log(float(idx.iloc[-1])))
    last["segment"] = last["comp_std"].map(bucket)
    last["cnt365"] = last["n365"]
    last["days_since"] = (stats_end - last["last_tx"]).dt.days.clip(lower=0)
    last["confidence"] = [
        confidence_score(
            ConfidenceInputs(
                same_complex_transactions_365d=int(r.cnt365),
                days_since_last_complex_tx=float(r.days_since),
                model_prediction_std=cal.seg_rel_std.get(r.segment, cal.global_rel_std),
                segment_backtest_accuracy=cal.seg_ppe10.get(r.segment, cal.global_ppe10),
            )
        )
        for r in last.itertuples()
    ]

    out_model = Path(f"models/{mid}")
    out_model.mkdir(parents=True, exist_ok=True)
    out_reports = Path(f"reports/backtest_{mid}")
    out_reports.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_model / "model.txt"))
    (out_model / "conformal.json").write_text(json.dumps(cal.to_json(), indent=1))
    cols = [
        "global_id",
        "local_id_canonical",
        "admin_level_2",
        "complex_id",
        "complex_name",
        "community_name",
        "net_area_sqm",
        "br_code",
        "transaction_date",
        "price",
        "value_now",
        "segment",
        "n_comps",
        "comp_std",
        "confidence",
        "cnt365",
        "days_since",
    ]
    last[cols].to_parquet(out_reports / "candidates.parquet")
    (out_reports / "report.md").write_text(
        f"# {mid}\n\n"
        f"Demo-grade Dubai apartment AVM (docs/08), hybrid: same-class comp\n"
        f"median x city index (liquid classes, n>={MIN_COMPS} in 730d — primary,\n"
        f"attested) + hedonic LightGBM (illiquid fallback, not attested).\n"
        f"Data: DLD open transactions mirror through {DATA_END:%Y-%m-%d}.\n"
        f"Split: train<= {TRAIN_END} / val<= {VAL_END} / holdout after.\n"
        f"Values are 'Valuation Estimates' (not RERA appraisals).\n"
        f"Identity = unit class (docs/08).\n",
        encoding="utf-8",
    )
    log.info(
        "artifacts_written",
        model=str(out_model),
        candidates=len(last),
        auto_issue=int((last["confidence"] >= 0.85).sum()),
    )
    print(f"MODEL_ID: {mid}")


if __name__ == "__main__":
    asyncio.run(main())
