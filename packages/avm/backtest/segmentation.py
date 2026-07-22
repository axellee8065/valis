"""Segment definitions for reporting (docs/03 §7, docs/04 §4).

Metrics must be reported per segment — never hide variance behind the mean.
"""

import numpy as np
import pandas as pd

GANGNAM_3GU = {"강남구", "서초구", "송파구"}

# 가격대 (USD) — 억원 근사 환산 기준 버킷은 KRW로 정의
PRICE_BUCKETS_KRW = [
    (0, 500_000_000, "~5억"),
    (500_000_000, 1_000_000_000, "5-10억"),
    (1_000_000_000, 2_000_000_000, "10-20억"),
    (2_000_000_000, float("inf"), "20억+"),
]

AREA_BUCKETS = [
    (0, 59.99, "~59㎡"),
    (60, 84.99, "60-84㎡"),
    (85, 114.99, "85-114㎡"),
    (115, float("inf"), "115㎡+"),
]

AGE_BUCKETS = [
    (0, 5, "신축(~5년)"),
    (6, 15, "준신축(6-15)"),
    (16, 30, "중고(16-30)"),
    (31, float("inf"), "노후(30+)"),
]

COMPLEX_SIZE_BUCKETS = [
    (0, 299, "소단지(~300)"),
    (300, 999, "중단지(300-1000)"),
    (1000, float("inf"), "대단지(1000+)"),
]


def _bucketize(series: pd.Series, buckets: list[tuple]) -> pd.Series:
    def assign(v):
        if pd.isna(v):
            return "__missing__"
        for lo, hi, label in buckets:
            if lo <= v <= hi:
                return label
        return "__missing__"

    return series.map(assign)


def add_segments(df: pd.DataFrame, price_col: str = "price_krw") -> pd.DataFrame:
    """Adds segment columns: seg_region, seg_price, seg_area, seg_age,
    seg_complex_size, seg_quarter."""
    out = df.copy()
    if "admin_level_2" in out:
        out["seg_region"] = np.where(out["admin_level_2"].isin(GANGNAM_3GU), "강남3구", "그 외")
    if price_col in out:
        out["seg_price"] = _bucketize(out[price_col].astype(float), PRICE_BUCKETS_KRW)
    if "net_area_sqm" in out:
        out["seg_area"] = _bucketize(out["net_area_sqm"].astype(float), AREA_BUCKETS)
    if "age_years" in out:
        out["seg_age"] = _bucketize(out["age_years"].astype(float), AGE_BUCKETS)
    if "units_in_building" in out:
        out["seg_complex_size"] = _bucketize(
            out["units_in_building"].astype(float), COMPLEX_SIZE_BUCKETS
        )
    if "transaction_date" in out:
        ts = pd.to_datetime(out["transaction_date"])
        out["seg_quarter"] = ts.dt.year.astype(str) + "Q" + ts.dt.quarter.astype(str)
    return out


SEGMENT_AXES = [
    "admin_level_2",
    "seg_region",
    "seg_price",
    "seg_area",
    "seg_age",
    "seg_complex_size",
    "seg_quarter",
]


def segment_metrics(df: pd.DataFrame, pred_col: str, actual_col: str) -> dict[str, pd.DataFrame]:
    """Per-axis metric tables. Returns {axis: DataFrame indexed by bucket}."""
    from packages.avm.backtest.metrics import compute_metrics

    tables: dict[str, pd.DataFrame] = {}
    for axis in SEGMENT_AXES:
        if axis not in df.columns:
            continue
        rows = []
        for bucket, g in df.groupby(axis):
            m = compute_metrics(g[pred_col].values, g[actual_col].values)
            rows.append({"segment": bucket, **m.to_dict()})
        tables[axis] = pd.DataFrame(rows).set_index("segment").sort_index()
    return tables
