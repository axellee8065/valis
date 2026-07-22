"""Comparison baselines B1–B4 (docs/04 §5).

Our model earns trust only relative to baselines.
"""

import numpy as np
import pandas as pd

from packages.avm.models.v0_median import predict_v0


def baseline_b1_kongsi_ratio(
    df: pd.DataFrame,
    kongsi_col: str = "kongsi_value",
    region_col: str = "admin_level_2",
    price_col: str = "price",
) -> pd.Series:
    """B1: 공시가격 × regional market ratio.

    Ratio per region = median(price / kongsi) computed on TRAINING rows only
    (pass a df with a boolean `is_train` column to avoid leakage).
    """
    out = pd.Series(np.nan, index=df.index)
    if kongsi_col not in df.columns:
        return out
    train = df[df.get("is_train", pd.Series(False, index=df.index))]
    if train.empty:
        return out
    ratios = (
        (train[price_col].astype(float) / train[kongsi_col].astype(float))
        .groupby(train[region_col])
        .median()
    )
    for region, g in df.groupby(region_col):
        r = ratios.get(region)
        if r is not None and not np.isnan(r):
            out.loc[g.index] = g[kongsi_col].astype(float) * r
    return out


def baseline_b2_complex_median(df: pd.DataFrame, transactions: pd.DataFrame) -> pd.Series:
    """B2: v0 model (same-complex recent median)."""
    preds = []
    for _, row in df.iterrows():
        p = predict_v0(
            complex_id=row["complex_id"],
            net_area_sqm=float(row["net_area_sqm"]),
            target_date=pd.Timestamp(row["transaction_date"]).date(),
            transactions=transactions,
        )
        preds.append(p if p is not None else np.nan)
    return pd.Series(preds, index=df.index)


def baseline_b4_index_estimate(
    df: pd.DataFrame,
    index_series: pd.Series,  # month (Period) -> index value (부동산원 R-ONE)
    anchor_price_col: str = "last_known_price",
    anchor_date_col: str = "last_known_date",
) -> pd.Series:
    """B4: scale the property's last known price by the regional index ratio."""
    out = pd.Series(np.nan, index=df.index)
    if anchor_price_col not in df.columns:
        return out
    for i, row in df.iterrows():
        anchor_p = row.get(anchor_price_col)
        anchor_d = row.get(anchor_date_col)
        if pd.isna(anchor_p) or pd.isna(anchor_d):
            continue
        m_then = pd.Timestamp(anchor_d).to_period("M")
        m_now = pd.Timestamp(row["transaction_date"]).to_period("M")
        if m_then in index_series.index and m_now in index_series.index:
            out.loc[i] = float(anchor_p) * index_series[m_now] / index_series[m_then]
    return out
