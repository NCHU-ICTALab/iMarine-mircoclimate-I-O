from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .metrics import WeatherMetrics


class CWAComparator:
    """Compare local model predictions with CWA forecasts against observations."""

    def __init__(self, cwa_forecast_data: pd.DataFrame, config: dict[str, Any] | None = None) -> None:
        self.cwa = cwa_forecast_data.copy()
        self.config = config or {}

    def compare(self, my_predictions: pd.DataFrame, observations: pd.DataFrame, variable: str) -> dict[str, Any]:
        frame = self._merge(my_predictions, observations, variable)
        cwa_col = f"cwa_{variable}"
        result = {
            "variable": variable,
            "sample_count": int(len(frame)),
            "model": self._calculate_metrics(frame[variable], frame[f"pred_{variable}"], variable),
        }
        if cwa_col in frame:
            result["cwa"] = self._calculate_metrics(frame[variable], frame[cwa_col], variable)
            model_mae = result["model"]["mae"]
            cwa_mae = result["cwa"]["mae"]
            result["model_beats_cwa"] = bool(model_mae is not None and cwa_mae is not None and model_mae < cwa_mae)
        return result

    def compare_by_scenarios(self, my_predictions: pd.DataFrame, observations: pd.DataFrame, variable: str) -> dict[str, Any]:
        merged = self._merge(my_predictions, observations, variable)
        scenarios = self._define_scenarios(merged, variable)
        return {name: self.compare(merged.loc[mask], merged.loc[mask], variable) for name, mask in scenarios.items() if bool(mask.any())}

    def generate_comparison_report(self, comparison_results: dict[str, Any], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# CWA Comparison Report", ""]
        for key, value in comparison_results.items():
            lines.append(f"## {key}")
            if isinstance(value, dict):
                for metric, metric_value in value.items():
                    lines.append(f"- {metric}: {metric_value}")
            else:
                lines.append(str(value))
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _merge(self, my_predictions: pd.DataFrame, observations: pd.DataFrame, variable: str) -> pd.DataFrame:
        pred = _indexed(my_predictions)
        obs = _indexed(observations)
        cwa = _indexed(self.cwa)
        pred_col = f"pred_{variable}"
        if variable in pred.columns and pred_col not in pred.columns:
            pred = pred.rename(columns={variable: pred_col})
        cwa_col = f"cwa_{variable}"
        if variable in cwa.columns and cwa_col not in cwa.columns:
            cwa = cwa.rename(columns={variable: cwa_col})
        merged = obs.join(pred[[pred_col]], how="inner")
        if cwa_col in cwa:
            merged = merged.join(cwa[[cwa_col]], how="left")
        return merged.dropna(subset=[variable, pred_col])

    def _calculate_metrics(self, y_true: Any, y_pred: Any, variable: str) -> dict[str, Any]:
        metrics = WeatherMetrics.regression_scores(y_true, y_pred)
        if "rain" in variable or "precipitation" in variable:
            metrics["rainfall"] = WeatherMetrics.rainfall_scores(y_true, y_pred, threshold=float(self.config.get("rain_threshold", 0.1)))
        return metrics

    def _define_scenarios(self, observations: pd.DataFrame, variable: str) -> dict[str, pd.Series]:
        values = observations[variable]
        scenarios = {
            "all": pd.Series(True, index=observations.index),
            "high": values >= values.quantile(0.9),
            "low": values <= values.quantile(0.1),
        }
        if "rain" in variable or "precipitation" in variable:
            threshold = float(self.config.get("rain_threshold", 0.1))
            scenarios["rainy"] = values >= threshold
            scenarios["dry"] = values < threshold
        return scenarios


def _indexed(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.set_index("timestamp")
    elif "obs_time" in out.columns:
        out["obs_time"] = pd.to_datetime(out["obs_time"])
        out = out.set_index("obs_time")
    return out.sort_index()
