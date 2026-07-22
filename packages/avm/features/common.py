"""Country-agnostic feature engineering (docs/03 §2, docs/06 §3.3).

Anti-leakage rules (docs/03 §2.6 — non-negotiable):
- Never use information dated after the transaction date.
- Rolling windows always exclude the current transaction.
"""

import numpy as np
import pandas as pd

MISSING_CAT = "__missing__"

AGE_BUCKETS = [(0, 5), (6, 10), (11, 20), (21, 30), (31, 999)]


def age_bucket(age_years: float | int | None) -> str:
    if age_years is None or (isinstance(age_years, float) and np.isnan(age_years)):
        return MISSING_CAT
    for lo, hi in AGE_BUCKETS:
        if lo <= age_years <= hi:
            return f"{lo}-{hi if hi < 999 else '+'}"
    return MISSING_CAT


def add_intrinsic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derived intrinsic features. Expects columns:
    net_area_sqm, floor_number, floors_total, built_year, transaction_date,
    units_in_building (optional).
    """
    out = df.copy()
    out["log_net_area"] = np.log(out["net_area_sqm"].astype(float))
    if "floors_total" in out:
        ft = out["floors_total"].replace(0, np.nan)
        out["floor_ratio"] = out["floor_number"] / ft
        out["is_top_floor"] = (out["floor_number"] == out["floors_total"]).fillna(False)
    out["is_ground_floor"] = out["floor_number"] == 1
    tx_year = pd.to_datetime(out["transaction_date"]).dt.year
    out["age_years"] = (tx_year - out["built_year"]).clip(lower=0)
    out["age_bucket"] = out["age_years"].map(age_bucket)
    if "units_in_building" in out:
        out["is_large_complex"] = out["units_in_building"] >= 1000
    return out


def add_complex_rolling_features(df: pd.DataFrame, window_days: int = 365) -> pd.DataFrame:
    """Complex-level rolling features, strictly excluding the current row and
    any transaction on/after the current transaction_date (no leakage).

    Expects: complex_id, transaction_date, price (numeric), net_area_sqm.
    O(n²) within complex — fine for Seoul-scale monthly batches; optimize later.
    """
    out = df.copy()
    out["_ppm"] = out["price"].astype(float) / out["net_area_sqm"].astype(float)
    dates = pd.to_datetime(out["transaction_date"])

    med = np.full(len(out), np.nan)
    cnt = np.zeros(len(out), dtype=int)
    std = np.full(len(out), np.nan)
    last_days = np.full(len(out), np.nan)

    for _, idx in out.groupby("complex_id").groups.items():
        idx = list(idx)
        c_dates = dates.loc[idx]
        c_ppm = out.loc[idx, "_ppm"]
        for i in idx:
            t = dates.loc[i]
            mask = (c_dates < t) & (c_dates >= t - pd.Timedelta(days=window_days))
            prior = c_ppm[mask]
            pos = out.index.get_loc(i)
            cnt[pos] = len(prior)
            if len(prior) > 0:
                med[pos] = prior.median()
                std[pos] = prior.std() if len(prior) > 1 else 0.0
                last_days[pos] = (t - c_dates[mask].max()).days

    out["complex_median_ppm_365d"] = med
    out["complex_transaction_count_365d"] = cnt
    out["complex_ppm_std_365d"] = std
    out["complex_last_transaction_days_ago"] = last_days
    return out.drop(columns=["_ppm"])


def impute(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str]) -> pd.DataFrame:
    """Median imputation + missing flags for numeric; sentinel for categorical."""
    out = df.copy()
    for col in numeric_cols:
        if col in out:
            out[f"{col}__missing"] = out[col].isna()
            out[col] = out[col].fillna(out[col].median())
    for col in cat_cols:
        if col in out:
            out[col] = out[col].fillna(MISSING_CAT)
    return out
