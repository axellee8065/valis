"""AVM v0 — same-complex recent-median baseline (docs/03 §3.1).

Purpose: validate the pipeline end-to-end and establish a baseline.
Returns None when fewer than MIN_COMPARABLES prior transactions exist
(prediction refused rather than unreliable).
"""

from datetime import date, timedelta

import pandas as pd

MIN_COMPARABLES = 3
LOOKBACK_DAYS = 180


def predict_v0(
    complex_id: str,
    net_area_sqm: float,
    target_date: date,
    transactions: pd.DataFrame,
    lookback_days: int = LOOKBACK_DAYS,
    min_comparables: int = MIN_COMPARABLES,
) -> float | None:
    """Median price-per-sqm of same-complex sales in the lookback window,
    scaled by the subject's net area.

    `transactions` requires columns: complex_id, transaction_date (datetime-like),
    price, net_area_sqm. Cancelled/related-party rows must be pre-filtered.
    Only transactions strictly BEFORE target_date are used (temporal safety).
    """
    tx_dates = pd.to_datetime(transactions["transaction_date"]).dt.date
    cutoff_lo = target_date - timedelta(days=lookback_days)
    same_complex = transactions[
        (transactions["complex_id"] == complex_id)
        & (tx_dates < target_date)
        & (tx_dates >= cutoff_lo)
    ]
    if len(same_complex) < min_comparables:
        return None
    ppm = same_complex["price"].astype(float) / same_complex["net_area_sqm"].astype(float)
    return float(ppm.median() * net_area_sqm)
