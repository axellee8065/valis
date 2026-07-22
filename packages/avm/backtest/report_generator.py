"""Backtest report → Markdown (docs/04 §6–7). PDF export via pandoc later."""

import pandas as pd

from packages.avm.backtest.metrics import BacktestMetrics

TARGETS = {
    "mdape": ("MdAPE", 0.05, "≤ 5%"),
    "ppe10": ("PPE10", 0.85, "≥ 85%"),
    "ppe20": ("PPE20", 0.95, "≥ 95%"),
    "coverage": ("Coverage", 0.90, "≥ 90%"),
}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%" if pd.notna(x) else "n/a"


def _headline_table(m: BacktestMetrics) -> str:
    rows = [
        "| Metric | Value | Target | Pass |",
        "|---|---|---|---|",
        f"| MdAPE | {_pct(m.mdape)} | ≤ 5% (도전) / ≤ 7% (최소) | {'✅' if m.mdape <= 0.07 else '❌'} |",
        f"| MAPE | {_pct(m.mape)} | ≤ 8% | {'✅' if m.mape <= 0.08 else '❌'} |",
        f"| PPE10 | {_pct(m.ppe10)} | ≥ 75% (최소) / ≥ 85% (도전) | {'✅' if m.ppe10 >= 0.75 else '❌'} |",
        f"| PPE20 | {_pct(m.ppe20)} | ≥ 90% | {'✅' if m.ppe20 >= 0.90 else '❌'} |",
        f"| Coverage | {_pct(m.coverage)} | ≥ 85% | {'✅' if m.coverage >= 0.85 else '❌'} |",
        f"| Bias (median rel. err) | {_pct(m.median_relative_error)} | \\|bias\\| ≤ 1% | {'✅' if abs(m.median_relative_error) <= 0.01 else '❌'} |",
        f"| RMSE (log) | {m.rmse_log:.4f} | reference | — |",
        f"| N (holdout) | {m.n_total:,} | — | — |",
    ]
    return "\n".join(rows)


def _segment_section(segments: dict[str, pd.DataFrame]) -> str:
    parts = []
    for axis, table in segments.items():
        parts.append(f"\n### Segment: `{axis}`\n")
        cols = ["n_total", "coverage", "mdape", "ppe10", "ppe20", "median_relative_error"]
        view = table[[c for c in cols if c in table.columns]].copy()
        for c in ["coverage", "mdape", "ppe10", "ppe20", "median_relative_error"]:
            if c in view:
                view[c] = view[c].map(_pct)
        parts.append(view.to_markdown())
    return "\n".join(parts)


def _baseline_section(baselines: dict[str, BacktestMetrics], ours: BacktestMetrics) -> str:
    if not baselines:
        return "_No baselines computed for this run._"
    rows = ["| Model | MdAPE | PPE10 | Coverage |", "|---|---|---|---|"]
    rows.append(
        f"| **ours** | **{_pct(ours.mdape)}** | **{_pct(ours.ppe10)}** | **{_pct(ours.coverage)}** |"
    )
    for name, m in baselines.items():
        rows.append(f"| {name} | {_pct(m.mdape)} | {_pct(m.ppe10)} | {_pct(m.coverage)} |")
    return "\n".join(rows)


def render_report_md(
    model_id: str,
    overall: BacktestMetrics,
    segments: dict[str, pd.DataFrame],
    baselines: dict[str, BacktestMetrics],
    manifest: dict,
) -> str:
    return f"""# Valis Protocol — Backtest Report

**Model:** `{model_id}`
**Backtest:** `{manifest["backtest_id"]}` — {manifest["run_at"]}
**Code SHA:** `{manifest["code_git_sha"]}`
**Holdout window:** {manifest["split"]["holdout"][0]} ~ {manifest["split"]["holdout"][1]}

---

## 1. Headline Metrics (Holdout)

{_headline_table(overall)}

## 2. Baseline Comparison

{_baseline_section(baselines, overall)}

## 3. Segment Performance

{_segment_section(segments)}

## 4. Reproducibility

- Data checksum: `{manifest["data_snapshot"]["checksum"]}`
- Transactions: {manifest["data_snapshot"]["transaction_count"]:,}
- Python {manifest["python_env"]["python"]}, pandas {manifest["python_env"]["pandas"]}
- Temporal split (train / val / holdout): {manifest["split"]["train"]} / {manifest["split"]["val"]} / {manifest["split"]["holdout"]}

> Holdout data was never used for feature engineering, hyperparameter tuning,
> or model selection. Random splits are forbidden by methodology (docs/04 §1).
"""
