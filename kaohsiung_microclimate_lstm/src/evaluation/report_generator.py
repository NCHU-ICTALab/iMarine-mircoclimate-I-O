from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import WeatherMetrics


class ReportGenerator:
    """Generate lightweight Markdown evaluation reports."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def generate_model_report(
        self,
        model_name: str,
        y_true: Any,
        y_pred: Any,
        feature_importance: dict[str, float] | None = None,
        output_dir: str | Path = "results/reports",
        variable: str = "target",
    ) -> Path:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output / f"{model_name}_evaluation_{timestamp}.md"
        sections = [
            f"# {model_name} Evaluation Report",
            "",
            f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
            f"- Variable: {variable}",
            "",
            self._generate_basic_stats(y_true, y_pred),
            self._generate_metrics_table(y_true, y_pred, variable),
            self._generate_feature_importance_table(feature_importance or {}),
            self._generate_error_analysis(y_true, y_pred),
        ]
        path.write_text("\n".join(section for section in sections if section), encoding="utf-8")
        return path

    def _generate_basic_stats(self, y_true: Any, y_pred: Any) -> str:
        true = np.asarray(y_true, dtype=float)
        pred = np.asarray(y_pred, dtype=float)
        return "\n".join(
            [
                "## Basic Statistics",
                "",
                "| Statistic | Actual | Predicted |",
                "|---|---:|---:|",
                f"| Count | {true.size} | {pred.size} |",
                f"| Mean | {np.nanmean(true):.4f} | {np.nanmean(pred):.4f} |",
                f"| Std | {np.nanstd(true):.4f} | {np.nanstd(pred):.4f} |",
                f"| Min | {np.nanmin(true):.4f} | {np.nanmin(pred):.4f} |",
                f"| Max | {np.nanmax(true):.4f} | {np.nanmax(pred):.4f} |",
                "",
            ]
        )

    def _generate_metrics_table(self, y_true: Any, y_pred: Any, variable: str) -> str:
        metrics = WeatherMetrics.regression_scores(y_true, y_pred)
        rows = ["## Metrics", "", "| Metric | Value |", "|---|---:|"]
        for key in ("rmse", "mae", "r2", "mape", "medae", "bias"):
            value = metrics[key]
            rows.append(f"| {key.upper()} | {value:.4f} |" if isinstance(value, float) else f"| {key.upper()} | {value} |")
        if "rain" in variable or "precipitation" in variable:
            rain = WeatherMetrics.rainfall_scores(y_true, y_pred, threshold=float(self.config.get("rain_threshold", 0.1)))
            for key in ("pod", "far", "csi", "accuracy", "bias_score"):
                value = rain[key]
                rows.append(f"| {key.upper()} | {value:.4f} |" if isinstance(value, float) else f"| {key.upper()} | {value} |")
        rows.append("")
        return "\n".join(rows)

    def _generate_feature_importance_table(self, feature_importance: dict[str, float], top_n: int = 20) -> str:
        if not feature_importance:
            return ""
        rows = ["## Top Feature Importance", "", "| Feature | Importance |", "|---|---:|"]
        for feature, value in sorted(feature_importance.items(), key=lambda item: item[1], reverse=True)[:top_n]:
            rows.append(f"| {feature} | {float(value):.6f} |")
        rows.append("")
        return "\n".join(rows)

    def _generate_error_analysis(self, y_true: Any, y_pred: Any) -> str:
        true = np.asarray(y_true, dtype=float)
        pred = np.asarray(y_pred, dtype=float)
        errors = pred - true
        return "\n".join(
            [
                "## Error Analysis",
                "",
                f"- Mean error: {np.nanmean(errors):.4f}",
                f"- Median absolute error: {np.nanmedian(np.abs(errors)):.4f}",
                f"- 90th percentile absolute error: {np.nanpercentile(np.abs(errors), 90):.4f}",
                "",
            ]
        )
