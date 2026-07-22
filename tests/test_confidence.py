from packages.avm.confidence import (
    ConfidenceInputs,
    confidence_score,
    confidence_tier,
    to_bps,
)


def _inputs(**overrides):
    base = dict(
        same_complex_transactions_365d=20,
        days_since_last_complex_tx=0,
        model_prediction_std=0.05,
        segment_backtest_accuracy=0.95,
    )
    base.update(overrides)
    return ConfidenceInputs(**base)


def test_best_case_is_high_confidence():
    score = confidence_score(_inputs())
    assert score >= 0.99
    assert confidence_tier(score) == "AUTO_ISSUE"


def test_worst_case_is_refused():
    score = confidence_score(
        _inputs(
            same_complex_transactions_365d=0,
            days_since_last_complex_tx=400,
            model_prediction_std=0.35,
            segment_backtest_accuracy=0.60,
        )
    )
    assert score <= 0.10
    assert confidence_tier(score) == "REFUSE"


def test_anomaly_halves_score():
    normal = confidence_score(_inputs())
    flagged = confidence_score(_inputs(is_anomaly=True))
    assert flagged == round(normal * 0.5, 4)


def test_tiers():
    assert confidence_tier(0.90) == "AUTO_ISSUE"
    assert confidence_tier(0.70) == "REVIEW_RECOMMENDED"
    assert confidence_tier(0.30) == "REFUSE"


def test_bps():
    assert to_bps(0.8734) == 8734
    assert to_bps(1.0) == 10_000
