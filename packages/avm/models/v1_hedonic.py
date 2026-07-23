"""AVM v1 — per-district hedonic linear regression (docs/03 §3.2).

Target: log(price_per_sqm) — improves linearity and tames heteroscedasticity.
One model per 자치구 (25 models for Seoul).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

V1_NUMERIC_FEATURES = [
    "log_net_area",
    "floor_ratio",
    "age_years",
    "complex_median_ppm_365d",
    "complex_transaction_count_365d",
]


@dataclass
class HedonicModelSet:
    """One fitted linear model per district."""

    models: dict[str, Any] = field(default_factory=dict)  # district -> LinearRegression
    feature_cols: list[str] = field(default_factory=list)
    medians: dict[str, pd.Series] = field(default_factory=dict)  # per-district imputation


def train_v1(
    df: pd.DataFrame,
    district_col: str = "admin_level_2",
    feature_cols: list[str] | None = None,
    min_rows: int = 100,
) -> HedonicModelSet:
    """Expects feature-engineered df with `price`, `net_area_sqm`, features.
    Districts with < min_rows are skipped (fall back to v0 at predict time).
    """
    from sklearn.linear_model import LinearRegression  # lazy: heavy dep

    cols = feature_cols or V1_NUMERIC_FEATURES
    ms = HedonicModelSet(feature_cols=cols)

    y_all = np.log(df["price"].astype(float) / df["net_area_sqm"].astype(float))
    for district, g in df.groupby(district_col):
        if len(g) < min_rows:
            continue
        X = g[cols].astype(float)
        med = X.median()
        X = X.fillna(med)
        model = LinearRegression()
        model.fit(X.values, y_all.loc[g.index].values)
        ms.models[district] = model
        ms.medians[district] = med
    return ms


def predict_v1(
    ms: HedonicModelSet, df: pd.DataFrame, district_col: str = "admin_level_2"
) -> pd.Series:
    """Returns predicted price (not ppm); NaN where no district model exists."""
    preds = pd.Series(np.nan, index=df.index)
    for district, g in df.groupby(district_col):
        model = ms.models.get(district)
        if model is None:
            continue
        X = g[ms.feature_cols].astype(float).fillna(ms.medians[district])
        log_ppm = model.predict(X.values)
        preds.loc[g.index] = np.exp(log_ppm) * g["net_area_sqm"].astype(float)
    return preds
