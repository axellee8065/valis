from datetime import date

import pandas as pd
import pytest

from packages.avm.backtest.splits import (
    DEFAULT_SPLIT,
    TemporalSplit,
    split_transactions,
    walk_forward_windows,
)


def test_default_split_boundaries():
    assert DEFAULT_SPLIT.train_end < DEFAULT_SPLIT.val_start
    assert DEFAULT_SPLIT.val_end < DEFAULT_SPLIT.holdout_start


def test_invalid_split_rejected():
    with pytest.raises(ValueError):
        TemporalSplit(
            train_start=date(2020, 1, 1),
            train_end=date(2025, 1, 1),  # overlaps validation
            val_start=date(2024, 1, 1),
            val_end=date(2025, 6, 30),
            holdout_start=date(2025, 7, 1),
            holdout_end=date(2026, 6, 30),
        )


def test_split_transactions_no_leakage():
    df = pd.DataFrame(
        {
            "transaction_date": [
                "2021-05-01",  # train
                "2024-06-30",  # train (boundary)
                "2024-07-01",  # val (boundary)
                "2025-01-15",  # val
                "2025-07-01",  # holdout (boundary)
                "2026-06-30",  # holdout (boundary)
                "2019-12-31",  # outside → dropped
            ],
            "price": [1, 2, 3, 4, 5, 6, 7],
        }
    )
    train, val, holdout = split_transactions(df)
    assert list(train["price"]) == [1, 2]
    assert list(val["price"]) == [3, 4]
    assert list(holdout["price"]) == [5, 6]
    # No row in more than one window
    assert len(set(train.index) & set(val.index)) == 0
    assert len(set(val.index) & set(holdout.index)) == 0


def test_walk_forward_windows_are_valid():
    windows = walk_forward_windows(date(2020, 1, 1), date(2026, 6, 30))
    assert len(windows) >= 1
    for w in windows:
        assert w.train_end < w.val_start
        assert w.val_end < w.holdout_start
