"""Temporal splits (docs/04 §2). Random splits are FORBIDDEN.

Default 3-way split:
    Training    2020-01-01 ~ 2024-06-30
    Validation  2024-07-01 ~ 2025-06-30
    Holdout     2025-07-01 ~ 2026-06-30  (final report metrics ONLY — never tuned on)
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class TemporalSplit:
    train_start: date
    train_end: date
    val_start: date
    val_end: date
    holdout_start: date
    holdout_end: date

    def __post_init__(self) -> None:
        order = [
            self.train_start,
            self.train_end,
            self.val_start,
            self.val_end,
            self.holdout_start,
            self.holdout_end,
        ]
        if order != sorted(order):
            raise ValueError("split boundaries must be strictly temporal (train < val < holdout)")
        if self.train_end >= self.val_start or self.val_end >= self.holdout_start:
            raise ValueError("split windows must not overlap")


DEFAULT_SPLIT = TemporalSplit(
    train_start=date(2020, 1, 1),
    train_end=date(2024, 6, 30),
    val_start=date(2024, 7, 1),
    val_end=date(2025, 6, 30),
    holdout_start=date(2025, 7, 1),
    holdout_end=date(2026, 6, 30),
)


def split_transactions(
    df: pd.DataFrame, split: TemporalSplit = DEFAULT_SPLIT, date_col: str = "transaction_date"
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (train, val, holdout). Rows outside all windows are dropped."""
    d = pd.to_datetime(df[date_col]).dt.date
    train = df[(d >= split.train_start) & (d <= split.train_end)]
    val = df[(d >= split.val_start) & (d <= split.val_end)]
    holdout = df[(d >= split.holdout_start) & (d <= split.holdout_end)]
    return train, val, holdout


def walk_forward_windows(
    start: date, end: date, train_months: int = 54, step_months: int = 6
) -> list[TemporalSplit]:
    """Walk-forward splits for v3-v4 robustness checks (docs/04 §2.2)."""
    windows: list[TemporalSplit] = []
    cursor = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    while True:
        train_start = cursor
        train_end = train_start + pd.DateOffset(months=train_months) - pd.Timedelta(days=1)
        val_start = train_end + pd.Timedelta(days=1)
        val_end = val_start + pd.DateOffset(months=step_months) - pd.Timedelta(days=1)
        holdout_start = val_end + pd.Timedelta(days=1)
        holdout_end = holdout_start + pd.DateOffset(months=step_months) - pd.Timedelta(days=1)
        if holdout_end > end_ts:
            break
        windows.append(
            TemporalSplit(
                train_start.date(),
                train_end.date(),
                val_start.date(),
                val_end.date(),
                holdout_start.date(),
                holdout_end.date(),
            )
        )
        cursor = cursor + pd.DateOffset(months=step_months)
    return windows
