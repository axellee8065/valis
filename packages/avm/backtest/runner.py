"""End-to-end backtest runner (docs/04 §6).

Produces: summary.json, predictions.parquet, report.md, manifest.json.
"""

import hashlib
import json
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from packages.avm.backtest.metrics import BacktestMetrics, compute_metrics
from packages.avm.backtest.report_generator import render_report_md
from packages.avm.backtest.segmentation import add_segments, segment_metrics
from packages.avm.backtest.splits import TemporalSplit


@dataclass
class BacktestResult:
    backtest_id: str
    model_id: str
    overall: BacktestMetrics
    segments: dict[str, pd.DataFrame]
    baseline_metrics: dict[str, BacktestMetrics]
    output_dir: Path


def _data_checksum(df: pd.DataFrame) -> str:
    h = hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return f"sha256:{h.hexdigest()}"


def run_backtest(
    holdout_df: pd.DataFrame,
    pred_col: str,
    actual_col: str,
    model_id: str,
    split: TemporalSplit,
    output_dir: str | Path,
    baselines: dict[str, pd.Series] | None = None,
    code_git_sha: str = "unknown",
) -> BacktestResult:
    """holdout_df must contain pred_col, actual_col, and segment source columns.
    NaN in pred_col = refusal (counts against coverage)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(UTC)
    backtest_id = f"bt-{run_at:%Y%m%d}-{code_git_sha[:6]}"

    df = add_segments(holdout_df)
    overall = compute_metrics(df[pred_col].values, df[actual_col].values)
    segments = segment_metrics(df, pred_col, actual_col)

    baseline_metrics: dict[str, BacktestMetrics] = {}
    for name, series in (baselines or {}).items():
        baseline_metrics[name] = compute_metrics(series.values, df[actual_col].values)

    # --- artifacts ---
    summary = {
        "backtest_id": backtest_id,
        "model_id": model_id,
        "overall": overall.to_dict(),
        "baselines": {k: v.to_dict() for k, v in baseline_metrics.items()},
        "segments": {
            axis: table.reset_index().to_dict(orient="records") for axis, table in segments.items()
        },
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    try:
        df.to_parquet(out / "predictions.parquet")
    except ImportError:
        df.to_csv(out / "predictions.csv", index=False)  # pyarrow absent fallback

    manifest = {
        "backtest_id": backtest_id,
        "run_at": run_at.isoformat(),
        "model_id": model_id,
        "code_git_sha": code_git_sha,
        "data_snapshot": {
            "transaction_count": len(df),
            "checksum": _data_checksum(df[[actual_col]]),
        },
        "split": {
            "train": [str(split.train_start), str(split.train_end)],
            "val": [str(split.val_start), str(split.val_end)],
            "holdout": [str(split.holdout_start), str(split.holdout_end)],
        },
        "python_env": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    report = render_report_md(model_id, overall, segments, baseline_metrics, manifest)
    (out / "report.md").write_text(report, encoding="utf-8")

    return BacktestResult(backtest_id, model_id, overall, segments, baseline_metrics, out)
