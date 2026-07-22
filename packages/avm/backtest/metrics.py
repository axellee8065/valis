"""Backtest evaluation metrics (docs/04 §3).

All functions take aligned arrays of predictions and actuals (same length,
NaN predictions = model refused → counted against Coverage, excluded from
error metrics).
"""

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class BacktestMetrics:
    n_total: int
    n_predicted: int
    coverage: float  # % of transactions where model predicted
    mdape: float  # median absolute % error
    mape: float  # mean absolute % error
    ppe10: float  # % within ±10%
    ppe20: float  # % within ±20%
    rmse_log: float  # RMSE of log-price
    median_relative_error: float  # bias: median (pred-actual)/actual
    skew: float  # skewness of relative error

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(pred: np.ndarray, actual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if pred.shape != actual.shape:
        raise ValueError("pred and actual must have the same shape")
    mask = ~np.isnan(pred) & ~np.isnan(actual) & (actual > 0)
    return pred[mask], actual[mask]


def _skewness(x: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    m = x.mean()
    s = x.std()
    if s == 0:
        return 0.0
    return float(np.mean(((x - m) / s) ** 3))


def compute_metrics(pred, actual) -> BacktestMetrics:
    pred_arr = np.asarray(pred, dtype=float)
    actual_arr = np.asarray(actual, dtype=float)
    n_total = len(pred_arr)
    p, a = _clean(pred_arr, actual_arr)
    n_predicted = len(p)

    if n_predicted == 0:
        return BacktestMetrics(n_total, 0, 0.0, np.nan, np.nan, 0.0, 0.0, np.nan, np.nan, 0.0)

    rel_err = (p - a) / a
    ape = np.abs(rel_err)

    return BacktestMetrics(
        n_total=n_total,
        n_predicted=n_predicted,
        coverage=round(n_predicted / n_total, 4) if n_total else 0.0,
        mdape=round(float(np.median(ape)), 4),
        mape=round(float(np.mean(ape)), 4),
        ppe10=round(float(np.mean(ape <= 0.10)), 4),
        ppe20=round(float(np.mean(ape <= 0.20)), 4),
        rmse_log=round(float(np.sqrt(np.mean((np.log(p) - np.log(a)) ** 2))), 4),
        median_relative_error=round(float(np.median(rel_err)), 4),
        skew=round(_skewness(rel_err), 4),
    )


def ci_coverage(actual, ci_lower, ci_upper) -> float:
    """Coverage-95: % of actuals inside the predicted CI. Target 93–97%
    (lower → overconfident, higher → over-conservative)."""
    a = np.asarray(actual, dtype=float)
    lo = np.asarray(ci_lower, dtype=float)
    hi = np.asarray(ci_upper, dtype=float)
    mask = ~np.isnan(lo) & ~np.isnan(hi) & ~np.isnan(a)
    if mask.sum() == 0:
        return float("nan")
    inside = (a[mask] >= lo[mask]) & (a[mask] <= hi[mask])
    return round(float(inside.mean()), 4)


def median_ci_width(pred, ci_lower, ci_upper) -> float:
    """Median relative CI width. Target ≤ 20%."""
    p = np.asarray(pred, dtype=float)
    lo = np.asarray(ci_lower, dtype=float)
    hi = np.asarray(ci_upper, dtype=float)
    mask = ~np.isnan(p) & ~np.isnan(lo) & ~np.isnan(hi) & (p > 0)
    if mask.sum() == 0:
        return float("nan")
    return round(float(np.median((hi[mask] - lo[mask]) / p[mask])), 4)
