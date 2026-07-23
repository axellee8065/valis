import numpy as np
import pandas as pd
import pytest

from packages.avm.conformal import ConformalCalibrator


@pytest.fixture
def fitted():
    """Synthetic validation set: known ±10% log-normal error, two segments."""
    rng = np.random.default_rng(42)
    n = 5000
    actual = pd.Series(rng.uniform(3e8, 20e8, n))
    noise = rng.normal(0, 0.10, n)  # sd 10% in log space
    pred = actual * np.exp(-noise)
    segments = pd.Series(rng.choice(["강남구", "노원구"], n))
    return ConformalCalibrator.fit(pred, actual, segments), pred, actual, segments


class TestFit:
    def test_quantiles_match_known_noise(self, fitted):
        cal, *_ = fitted
        # 95% quantiles of N(0, 0.1) ≈ ±0.196
        assert cal.global_q_lo == pytest.approx(-0.196, abs=0.02)
        assert cal.global_q_hi == pytest.approx(+0.196, abs=0.02)
        assert cal.global_rel_std == pytest.approx(0.10, abs=0.01)

    def test_small_segments_fall_back_to_global(self):
        pred = pd.Series([1.0e9] * 300)
        actual = pd.Series([1.05e9] * 300)
        segments = pd.Series(["강남구"] * 250 + ["희귀구"] * 50)  # 50 < MIN_SEGMENT_ROWS
        cal = ConformalCalibrator.fit(pred, actual, segments)
        assert "강남구" in cal.seg_q_lo
        assert "희귀구" not in cal.seg_q_lo

    def test_refusals_excluded(self):
        pred = pd.Series([1e9, np.nan, 1e9] * 100)
        actual = pd.Series([1e9] * 300)
        cal = ConformalCalibrator.fit(pred, actual, pd.Series(["a"] * 300))
        assert np.isfinite(cal.global_q_lo)


class TestInterval:
    def test_empirical_coverage_near_95(self, fitted):
        cal, pred, actual, segments = fitted
        lo, hi = cal.interval(pred, segments)
        inside = ((actual >= lo) & (actual <= hi)).mean()
        assert inside == pytest.approx(0.95, abs=0.02)

    def test_interval_brackets_prediction(self, fitted):
        cal, pred, _, segments = fitted
        lo, hi = cal.interval(pred, segments)
        assert (lo < pred).all()
        assert (hi > pred).all()

    def test_unknown_segment_uses_global(self, fitted):
        cal, *_ = fitted
        lo, hi = cal.interval(pd.Series([1e9]), pd.Series(["미지의구"]))
        assert lo.iloc[0] == pytest.approx(1e9 * np.exp(cal.global_q_lo))
        assert hi.iloc[0] == pytest.approx(1e9 * np.exp(cal.global_q_hi))


class TestSerialization:
    def test_roundtrip(self, fitted):
        cal, pred, _, segments = fitted
        restored = ConformalCalibrator.from_json(cal.to_json())
        lo1, hi1 = cal.interval(pred[:10], segments[:10])
        lo2, hi2 = restored.interval(pred[:10], segments[:10])
        assert np.allclose(lo1, lo2)
        assert np.allclose(hi1, hi2)
