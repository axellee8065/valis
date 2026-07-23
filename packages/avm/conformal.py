"""Conformal prediction intervals (docs/03 §6.2 — recommended method).

Uses the fitted model's VALIDATION residuals as an empirical distribution:
per-segment log-residual quantiles give distribution-free 95% CIs with
finite-sample coverage guarantees. Segments with too few validation rows fall
back to the global quantiles.

CI:  [pred × exp(q_lo),  pred × exp(q_hi)]
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MIN_SEGMENT_ROWS = 200
DEFAULT_ALPHA = 0.05  # 95% CI


@dataclass
class ConformalCalibrator:
    alpha: float
    global_q_lo: float
    global_q_hi: float
    global_rel_std: float
    seg_q_lo: dict = field(default_factory=dict)
    seg_q_hi: dict = field(default_factory=dict)
    seg_rel_std: dict = field(default_factory=dict)
    seg_ppe10: dict = field(default_factory=dict)  # feeds confidence scoring
    global_ppe10: float = 0.0

    # --- fitting ---

    @classmethod
    def fit(
        cls,
        pred: pd.Series,
        actual: pd.Series,
        segments: pd.Series,
        alpha: float = DEFAULT_ALPHA,
    ) -> "ConformalCalibrator":
        """pred/actual: nominal prices on the VALIDATION set (never holdout —
        docs/04 §1). segments: segment key per row (e.g. admin_level_2)."""
        p = pred.astype(float)
        a = actual.astype(float)
        mask = p.notna() & a.notna() & (p > 0) & (a > 0)
        p, a, seg = p[mask], a[mask], segments[mask]

        resid = np.log(a) - np.log(p)
        ape = (p - a).abs() / a

        cal = cls(
            alpha=alpha,
            global_q_lo=float(resid.quantile(alpha / 2)),
            global_q_hi=float(resid.quantile(1 - alpha / 2)),
            global_rel_std=float(resid.std()),
            global_ppe10=float((ape <= 0.10).mean()),
        )
        for key, idx in resid.groupby(seg).groups.items():
            r = resid.loc[idx]
            if len(r) < MIN_SEGMENT_ROWS:
                continue
            cal.seg_q_lo[key] = float(r.quantile(alpha / 2))
            cal.seg_q_hi[key] = float(r.quantile(1 - alpha / 2))
            cal.seg_rel_std[key] = float(r.std())
            cal.seg_ppe10[key] = float((ape.loc[idx] <= 0.10).mean())
        return cal

    # --- lookups ---

    def interval(self, pred: pd.Series, segments: pd.Series) -> tuple[pd.Series, pd.Series]:
        q_lo = segments.map(lambda s: self.seg_q_lo.get(s, self.global_q_lo))
        q_hi = segments.map(lambda s: self.seg_q_hi.get(s, self.global_q_hi))
        p = pred.astype(float)
        return p * np.exp(q_lo.astype(float)), p * np.exp(q_hi.astype(float))

    def rel_std(self, segments: pd.Series) -> pd.Series:
        return segments.map(lambda s: self.seg_rel_std.get(s, self.global_rel_std)).astype(float)

    def ppe10(self, segments: pd.Series) -> pd.Series:
        return segments.map(lambda s: self.seg_ppe10.get(s, self.global_ppe10)).astype(float)

    # --- (de)serialization for model artifacts ---

    def to_json(self) -> dict:
        return {
            "alpha": self.alpha,
            "global": {
                "q_lo": self.global_q_lo,
                "q_hi": self.global_q_hi,
                "rel_std": self.global_rel_std,
                "ppe10": self.global_ppe10,
            },
            "segments": {
                str(k): {
                    "q_lo": self.seg_q_lo[k],
                    "q_hi": self.seg_q_hi[k],
                    "rel_std": self.seg_rel_std[k],
                    "ppe10": self.seg_ppe10[k],
                }
                for k in self.seg_q_lo
            },
        }

    @classmethod
    def from_json(cls, data: dict) -> "ConformalCalibrator":
        g = data["global"]
        cal = cls(
            alpha=data["alpha"],
            global_q_lo=g["q_lo"],
            global_q_hi=g["q_hi"],
            global_rel_std=g["rel_std"],
            global_ppe10=g["ppe10"],
        )
        for k, v in data.get("segments", {}).items():
            cal.seg_q_lo[k] = v["q_lo"]
            cal.seg_q_hi[k] = v["q_hi"]
            cal.seg_rel_std[k] = v["rel_std"]
            cal.seg_ppe10[k] = v["ppe10"]
        return cal
