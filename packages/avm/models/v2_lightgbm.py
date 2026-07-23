"""AVM v2 — single LightGBM model for all of Seoul (docs/03 §3.3).

Target: log(price). District/dong enter as native categorical features.
Reproducibility: random_state=42, library versions recorded in the manifest.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

RANDOM_STATE = 42

V2_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "n_estimators": 2000,
    "learning_rate": 0.03,
    "num_leaves": 63,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "random_state": RANDOM_STATE,
    "verbosity": -1,
}

V2_CATEGORICAL = ["admin_level_2", "admin_level_3", "heating_type", "structure_code", "age_bucket"]

V2_NUMERIC = [
    "log_net_area",
    "net_area_sqm",
    "floor_number",
    "floor_ratio",
    "is_top_floor",
    "is_ground_floor",
    "age_years",
    "units_in_building",  # 대단지 프리미엄 (세움터 enrichment)
    "is_large_complex",
    "floors_total",
    "complex_median_ppm_365d",
    "complex_transaction_count_365d",
    "complex_ppm_std_365d",
    "complex_last_transaction_days_ago",
]


@dataclass
class V2Model:
    booster: Any  # lightgbm.LGBMRegressor | lightgbm.Booster
    feature_cols: list[str]
    categorical_cols: list[str]


def _prepare(df: pd.DataFrame, feature_cols: list[str], cat_cols: list[str]) -> pd.DataFrame:
    X = df[[c for c in feature_cols if c in df.columns]].copy()
    for c in X.columns:
        if c in cat_cols:
            X[c] = X[c].astype("category")
        else:
            # DB Numeric columns arrive as Decimal (object dtype) — LightGBM
            # requires int/float/bool
            X[c] = pd.to_numeric(X[c], errors="coerce")
    return X


def train_v2(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    numeric: list[str] | None = None,
    categorical: list[str] | None = None,
    params: dict | None = None,
) -> V2Model:
    import lightgbm as lgb  # lazy: heavy dep

    num = [c for c in (numeric or V2_NUMERIC) if c in train_df.columns]
    cat = [c for c in (categorical or V2_CATEGORICAL) if c in train_df.columns]
    cols = num + cat

    X_train = _prepare(train_df, cols, cat)
    y_train = np.log(train_df["price"].astype(float))
    X_val = _prepare(val_df, cols, cat)
    y_val = np.log(val_df["price"].astype(float))

    model = lgb.LGBMRegressor(**(params or V2_PARAMS))
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(100, verbose=False)],
        categorical_feature=cat,
    )
    return V2Model(booster=model, feature_cols=cols, categorical_cols=cat)


def load_v2(model_dir: str | Path) -> V2Model:
    """Load a saved v2 artifact (model.txt + feature_config.json)."""
    import lightgbm as lgb  # lazy: heavy dep

    model_dir = Path(model_dir)
    cfg = json.loads((model_dir / "feature_config.json").read_text())
    booster = lgb.Booster(model_file=str(model_dir / "model.txt"))
    return V2Model(
        booster=booster,
        feature_cols=cfg["feature_cols"],
        categorical_cols=cfg["categorical_cols"],
    )


def predict_v2(model: V2Model, df: pd.DataFrame) -> pd.Series:
    X = _prepare(df, model.feature_cols, model.categorical_cols)
    log_price = model.booster.predict(X)
    return pd.Series(np.exp(log_price), index=df.index)


def save_v2(model: V2Model, out_dir: str | Path, metrics: dict, manifest: dict) -> None:
    """Persist artifacts per docs/03 §4: model.txt, feature_config.json,
    metrics.json, training_data_manifest.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    model.booster.booster_.save_model(str(out / "model.txt"))
    (out / "feature_config.json").write_text(
        json.dumps(
            {"feature_cols": model.feature_cols, "categorical_cols": model.categorical_cols},
            indent=2,
        )
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out / "training_data_manifest.json").write_text(json.dumps(manifest, indent=2))
