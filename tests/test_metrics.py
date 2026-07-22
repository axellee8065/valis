import numpy as np
import pytest

from packages.avm.backtest.metrics import ci_coverage, compute_metrics, median_ci_width


def test_perfect_predictions():
    actual = np.array([100.0, 200.0, 300.0])
    m = compute_metrics(actual, actual)
    assert m.mdape == 0.0
    assert m.ppe10 == 1.0
    assert m.ppe20 == 1.0
    assert m.coverage == 1.0
    assert m.median_relative_error == 0.0


def test_known_errors():
    actual = np.array([100.0, 100.0, 100.0, 100.0])
    pred = np.array([105.0, 95.0, 115.0, 100.0])  # APEs: 5%, 5%, 15%, 0%
    m = compute_metrics(pred, actual)
    assert m.mdape == 0.05
    assert m.ppe10 == 0.75
    assert m.ppe20 == 1.0


def test_refusals_hit_coverage_not_error():
    actual = np.array([100.0, 100.0, 100.0, 100.0])
    pred = np.array([100.0, np.nan, np.nan, 100.0])
    m = compute_metrics(pred, actual)
    assert m.coverage == 0.5
    assert m.n_predicted == 2
    assert m.mdape == 0.0  # refused rows excluded from error metrics


def test_bias_direction():
    actual = np.array([100.0] * 5)
    pred = np.array([110.0] * 5)  # systematic +10%
    m = compute_metrics(pred, actual)
    assert m.median_relative_error == pytest.approx(0.10)


def test_all_refused():
    m = compute_metrics(np.array([np.nan, np.nan]), np.array([1.0, 2.0]))
    assert m.coverage == 0.0
    assert m.n_predicted == 0


def test_ci_coverage():
    actual = np.array([100.0, 100.0, 100.0, 100.0])
    lo = np.array([90.0, 90.0, 101.0, 90.0])
    hi = np.array([110.0, 110.0, 110.0, 99.0])
    assert ci_coverage(actual, lo, hi) == 0.5


def test_median_ci_width():
    pred = np.array([100.0, 200.0])
    lo = np.array([90.0, 180.0])
    hi = np.array([110.0, 220.0])
    assert median_ci_width(pred, lo, hi) == pytest.approx(0.2)
