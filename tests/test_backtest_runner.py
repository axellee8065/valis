"""End-to-end backtest runner on synthetic data — exercises runner,
segmentation, and report generation together (the M2 exit-criteria path)."""

import json

import numpy as np
import pandas as pd
import pytest

from packages.avm.backtest.runner import run_backtest
from packages.avm.backtest.segmentation import add_segments, segment_metrics
from packages.avm.backtest.splits import DEFAULT_SPLIT


@pytest.fixture
def holdout_df():
    rng = np.random.default_rng(42)
    n = 400
    actual = rng.uniform(5e8, 2e9, n)
    pred = actual * rng.normal(1.0, 0.05, n)
    pred[:10] = np.nan  # refusals count against coverage
    return pd.DataFrame(
        {
            "prediction": pred,
            "price": actual,
            "price_krw": actual,
            "admin_level_2": rng.choice(["강남구", "서초구", "노원구", "마포구"], n),
            "net_area_sqm": rng.uniform(40, 120, n),
            "age_years": rng.integers(0, 40, n),
            "units_in_building": rng.integers(100, 2000, n),
            "transaction_date": pd.to_datetime(
                rng.choice(pd.date_range("2025-07-01", "2026-06-30"), n)
            ),
        }
    )


def test_run_backtest_end_to_end(tmp_path, holdout_df):
    result = run_backtest(
        holdout_df=holdout_df,
        pred_col="prediction",
        actual_col="price",
        model_id="avm-kr-seoul-apt-v2-20260101-abc123",
        split=DEFAULT_SPLIT,
        output_dir=tmp_path,
        code_git_sha="abc123",
    )
    # ~5% noise → MdAPE around 3-4%, refusals → coverage 97.5%
    assert result.overall.mdape < 0.06
    assert result.overall.coverage == pytest.approx(390 / 400, abs=0.001)

    # artifacts (docs/04 §6.2)
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "manifest.json").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["model_id"] == "avm-kr-seoul-apt-v2-20260101-abc123"
    assert "seg_quarter" in summary["segments"]

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "MdAPE" in report and "Reproducibility" in report


def test_segments_cover_all_axes(holdout_df):
    df = add_segments(holdout_df)
    for col in [
        "seg_region",
        "seg_price",
        "seg_area",
        "seg_age",
        "seg_complex_size",
        "seg_quarter",
    ]:
        assert col in df.columns
    assert set(df["seg_region"].unique()) <= {"강남3구", "그 외"}

    tables = segment_metrics(df, "prediction", "price")
    assert "admin_level_2" in tables
    # per-district rows sum to total
    assert tables["admin_level_2"]["n_total"].sum() == len(df)


def test_baselines_b2_on_synthetic(holdout_df):
    from packages.avm.backtest.baselines import baseline_b2_complex_median

    tx = pd.DataFrame(
        {
            "complex_id": ["C1"] * 5,
            "transaction_date": pd.to_datetime(
                ["2025-01-10", "2025-02-15", "2025-03-01", "2025-04-20", "2025-05-01"]
            ),
            "price": [8.5e8, 9e8, 8.8e8, 9.1e8, 8.9e8],
            "net_area_sqm": [84.99] * 5,
        }
    )
    subject = pd.DataFrame(
        {
            "complex_id": ["C1", "C2"],
            "net_area_sqm": [84.99, 59.0],
            "transaction_date": pd.to_datetime(["2025-07-01", "2025-07-01"]),
        }
    )
    preds = baseline_b2_complex_median(subject, tx)
    assert preds.iloc[0] == pytest.approx(8.9e8, rel=0.01)  # C1 median
    assert np.isnan(preds.iloc[1])  # unknown complex refused
