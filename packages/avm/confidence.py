"""AVM v4 — confidence scoring (docs/03 §3.5).

confidence = weighted_avg([liquidity, freshness, model certainty, segment accuracy])
Weights are tuned by backtest; defaults are the design-doc starting point.

Tiers:
- >= 0.85: auto-issue
- 0.60–0.85: issue with "review recommended" flag
- < 0.60: refuse (consensus route post-MVP)
"""

from dataclasses import dataclass

AUTO_ISSUE_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.60

DEFAULT_WEIGHTS = {
    "liquidity": 0.30,
    "freshness": 0.25,
    "model_certainty": 0.25,
    "segment_accuracy": 0.20,
}


def _normalize(value: float, lo: float, hi: float) -> float:
    """Clamp-normalize value into [0, 1] over [lo, hi]."""
    if hi == lo:
        return 0.0
    return min(1.0, max(0.0, (value - lo) / (hi - lo)))


@dataclass(frozen=True)
class ConfidenceInputs:
    same_complex_transactions_365d: int
    days_since_last_complex_tx: float
    model_prediction_std: float  # relative std of prediction (e.g. CI width proxy)
    segment_backtest_accuracy: float  # PPE10 of the subject's segment, 0-1
    is_anomaly: bool = False


def confidence_score(inputs: ConfidenceInputs, weights: dict[str, float] | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    components = {
        "liquidity": _normalize(inputs.same_complex_transactions_365d, 0, 20),
        "freshness": 1.0 - _normalize(inputs.days_since_last_complex_tx, 0, 365),
        "model_certainty": 1.0 - _normalize(inputs.model_prediction_std, 0.05, 0.30),
        "segment_accuracy": _normalize(inputs.segment_backtest_accuracy, 0.70, 0.95),
    }
    total_w = sum(w.values())
    score = sum(components[k] * w[k] for k in components) / total_w
    if inputs.is_anomaly:
        score *= 0.5  # anomaly-flagged cases are auto-downgraded (docs/03 §3.5)
    return round(score, 4)


def confidence_tier(score: float) -> str:
    if score >= AUTO_ISSUE_THRESHOLD:
        return "AUTO_ISSUE"
    if score >= REVIEW_THRESHOLD:
        return "REVIEW_RECOMMENDED"
    return "REFUSE"


def to_bps(score: float) -> int:
    return round(score * 10_000)
