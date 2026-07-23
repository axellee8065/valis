"""AVM v3 — repeat-sales index time adjustment (docs/03 §3.4).

Problem solved: v2 anchors to the training window's price level, so predictions
drift as the market moves after the training cutoff (observed: holdout bias
-2.6% → -5.8% by quarter).

Method (Bailey–Muth–Nourse):
1. Build repeat-sale pairs (same unit sold twice) from non-cancelled sales.
2. Regress log price ratios on month dummies → monthly log index.
3. Train target becomes log(price / index[month])  (detrended).
4. Prediction = exp(model output) × index[target month]  (rescaled).

Anti-leakage: index[m] is estimated using ONLY pairs whose second sale is in
or before month m (expanding estimation). A transaction in month m may use
other transactions of that same month — market indices are observable
within-month (MOLIT reports within 30 days); the subject's own pair
contribution is negligible at Seoul scale.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_HOLDING_DAYS = 90  # filter flips / same-day corrections
MAX_ABS_DLOG = np.log(3.0)  # discard >3x or <1/3x ratios (data errors)
MIN_PAIRS_PER_MONTH = 30  # months with fewer pairs inherit the previous value


@dataclass
class RepeatSalesIndex:
    """Monthly index, base month = 1.0. Keys are 'YYYY-MM' strings."""

    values: dict[str, float]

    def at(self, month: str | pd.Period) -> float:
        key = str(pd.Period(month, freq="M"))
        if key in self.values:
            return self.values[key]
        # outside range → nearest known month (never extrapolate trends)
        known = sorted(self.values)
        if not known:
            return 1.0
        if key < known[0]:
            return self.values[known[0]]
        return self.values[max(k for k in known if k <= key)]

    def to_json(self) -> dict:
        return dict(self.values)

    @classmethod
    def from_json(cls, data: dict) -> "RepeatSalesIndex":
        return cls(values={k: float(v) for k, v in data.items()})


def build_repeat_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Consecutive sale pairs per unit. Expects: global_id, transaction_date,
    price (numeric). Returns columns: m1, m2 (Period[M]), dlog.
    Caller must pre-filter cancelled/related-party rows."""
    d = df[["global_id", "transaction_date", "price"]].copy()
    d["transaction_date"] = pd.to_datetime(d["transaction_date"])
    d["price"] = d["price"].astype(float)
    d = d.sort_values(["global_id", "transaction_date"])

    prev = d.groupby("global_id").shift(1)
    mask = prev["price"].notna()
    holding_days = (d["transaction_date"] - prev["transaction_date"]).dt.days
    dlog = np.log(d["price"] / prev["price"])
    mask &= holding_days >= MIN_HOLDING_DAYS
    mask &= dlog.abs() <= MAX_ABS_DLOG

    pairs = pd.DataFrame(
        {
            "m1": prev.loc[mask, "transaction_date"].dt.to_period("M"),
            "m2": d.loc[mask, "transaction_date"].dt.to_period("M"),
            "dlog": dlog[mask],
        }
    )
    return pairs[pairs["m1"] != pairs["m2"]].reset_index(drop=True)


def _bmn_solve(pairs: pd.DataFrame, months: list[pd.Period]) -> np.ndarray:
    """BMN least squares → log index per month (first month pinned to 0)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import lsqr

    pos = {m: i for i, m in enumerate(months)}
    n, k = len(pairs), len(months)
    rows = np.repeat(np.arange(n), 2)
    cols = np.empty(2 * n, dtype=int)
    vals = np.empty(2 * n)
    cols[0::2] = pairs["m1"].map(pos).to_numpy()
    vals[0::2] = -1.0
    cols[1::2] = pairs["m2"].map(pos).to_numpy()
    vals[1::2] = 1.0

    # pin base month: drop column 0
    keep = cols != 0
    x = coo_matrix((vals[keep], (rows[keep], cols[keep] - 1)), shape=(n, k - 1))
    beta = lsqr(x.tocsr(), pairs["dlog"].to_numpy())[0]
    return np.concatenate([[0.0], beta])


def compute_expanding_index(df: pd.DataFrame) -> RepeatSalesIndex:
    """index[m] = BMN estimate at month m using pairs with second sale ≤ m.

    One sparse least-squares solve per month over the expanding pair set —
    each month's value only ever sees information available at that time.
    """
    pairs = build_repeat_pairs(df)
    if pairs.empty:
        return RepeatSalesIndex(values={})

    all_dates = pd.to_datetime(df["transaction_date"])
    months = pd.period_range(all_dates.min(), all_dates.max(), freq="M").tolist()

    values: dict[str, float] = {}
    prev_val = 1.0
    for i, m in enumerate(months):
        window = pairs[pairs["m2"] <= m]
        if len(window) < MIN_PAIRS_PER_MONTH or i == 0:
            values[str(m)] = prev_val
            continue
        sub_months = months[: i + 1]
        log_idx = _bmn_solve(window, sub_months)
        prev_val = float(np.exp(log_idx[i]))
        values[str(m)] = prev_val
    return RepeatSalesIndex(values=values)


GANGNAM_3GU = {"강남구", "서초구", "송파구"}
MIN_GROUP_PAIRS = 2_000  # below this a group falls back to the citywide index


def region_group(admin_level_2: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(admin_level_2.isin(GANGNAM_3GU), "gangnam3", "other"),
        index=admin_level_2.index,
    )


def compute_group_indices(
    df: pd.DataFrame, group_col: str = "idx_group"
) -> dict[str, RepeatSalesIndex]:
    """Per-region expanding indices + citywide fallback under '__all__'.

    Premium regions appreciate on their own trajectory (observed: 강남3구 bias
    -8.6% under a citywide index) — one index per region group fixes that.
    Groups with too few repeat pairs inherit the citywide index.
    """
    citywide = compute_expanding_index(df)
    out: dict[str, RepeatSalesIndex] = {"__all__": citywide}
    for group, g in df.groupby(group_col):
        if len(build_repeat_pairs(g)) >= MIN_GROUP_PAIRS:
            out[str(group)] = compute_expanding_index(g)
        else:
            out[str(group)] = citywide
    return out


def detrend_prices_grouped(
    df: pd.DataFrame, indices: dict[str, RepeatSalesIndex], group_col: str = "idx_group"
) -> pd.Series:
    months = pd.to_datetime(df["transaction_date"]).dt.to_period("M").astype(str)
    factors = pd.Series(
        [
            indices.get(g, indices["__all__"]).at(m)
            for g, m in zip(df[group_col], months, strict=True)
        ],
        index=df.index,
    )
    return df["price"].astype(float) / factors


def rescale_predictions_grouped(
    detrended_pred: pd.Series,
    df: pd.DataFrame,
    indices: dict[str, RepeatSalesIndex],
    group_col: str = "idx_group",
) -> pd.Series:
    months = pd.to_datetime(df["transaction_date"]).dt.to_period("M").astype(str)
    factors = pd.Series(
        [
            indices.get(g, indices["__all__"]).at(m)
            for g, m in zip(df[group_col], months, strict=True)
        ],
        index=df.index,
    )
    return detrended_pred * factors


def detrend_prices(df: pd.DataFrame, index: RepeatSalesIndex) -> pd.Series:
    """price / index[month of transaction] — the v3 training target base."""
    months = pd.to_datetime(df["transaction_date"]).dt.to_period("M").astype(str)
    factors = months.map(lambda m: index.at(m))
    return df["price"].astype(float) / factors


def rescale_predictions(
    detrended_pred: pd.Series, df: pd.DataFrame, index: RepeatSalesIndex
) -> pd.Series:
    """Inverse of detrend at the prediction dates."""
    months = pd.to_datetime(df["transaction_date"]).dt.to_period("M").astype(str)
    factors = months.map(lambda m: index.at(m))
    return detrended_pred * factors
