from __future__ import annotations

from typing import Iterable

import numpy as np


class WeatherMetrics:
    """Weather forecast evaluation metrics from the v2.0 specification."""

    @staticmethod
    def _arrays(y_true: Iterable[float], y_pred: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
        true = np.asarray(y_true, dtype=float)
        pred = np.asarray(y_pred, dtype=float)
        if true.shape != pred.shape:
            raise ValueError(f"Shape mismatch: y_true={true.shape}, y_pred={pred.shape}")
        mask = np.isfinite(true) & np.isfinite(pred)
        return true[mask], pred[mask]

    @staticmethod
    def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        return float(np.sqrt(np.mean((true - pred) ** 2)))

    @staticmethod
    def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        return float(np.mean(np.abs(true - pred)))

    @staticmethod
    def r2(y_true: Iterable[float], y_pred: Iterable[float]) -> float | None:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        denom = float(np.sum((true - np.mean(true)) ** 2))
        if denom <= 0:
            return None
        return 1.0 - float(np.sum((true - pred) ** 2)) / denom

    @staticmethod
    def mape(y_true: Iterable[float], y_pred: Iterable[float], epsilon: float = 1e-10) -> float:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        return float(np.mean(np.abs((true - pred) / (true + epsilon))) * 100)

    @staticmethod
    def medae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        return float(np.median(np.abs(true - pred)))

    @staticmethod
    def bias(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        return float(np.mean(pred - true))

    @staticmethod
    def quantile_errors(
        y_true: Iterable[float],
        y_pred: Iterable[float],
        quantiles: Iterable[float] = (0.1, 0.25, 0.5, 0.75, 0.9),
    ) -> dict[str, float]:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        errors = np.abs(true - pred)
        return {f"q{int(q * 100):02d}": float(np.quantile(errors, q)) for q in quantiles}

    @staticmethod
    def skill_score(
        y_true: Iterable[float],
        y_pred: Iterable[float],
        y_baseline: Iterable[float],
    ) -> float | None:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        baseline_true, baseline = WeatherMetrics._arrays(y_true, y_baseline)
        if not np.array_equal(true, baseline_true):
            raise ValueError("Baseline array must align with y_true after finite filtering")
        model_mse = float(np.mean((true - pred) ** 2))
        baseline_mse = float(np.mean((true - baseline) ** 2))
        if baseline_mse <= 0:
            return None
        return 1.0 - model_mse / baseline_mse

    @staticmethod
    def regression_scores(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float | None | dict[str, float]]:
        return {
            "rmse": WeatherMetrics.rmse(y_true, y_pred),
            "mae": WeatherMetrics.mae(y_true, y_pred),
            "r2": WeatherMetrics.r2(y_true, y_pred),
            "mape": WeatherMetrics.mape(y_true, y_pred),
            "medae": WeatherMetrics.medae(y_true, y_pred),
            "bias": WeatherMetrics.bias(y_true, y_pred),
            "quantile_errors": WeatherMetrics.quantile_errors(y_true, y_pred),
        }

    @staticmethod
    def rainfall_scores(y_true: Iterable[float], y_pred: Iterable[float], threshold: float = 0.1) -> dict[str, float | int | None]:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        true_class = true >= threshold
        pred_class = pred >= threshold
        hits = int(np.sum(true_class & pred_class))
        misses = int(np.sum(true_class & ~pred_class))
        false_alarms = int(np.sum(~true_class & pred_class))
        correct_negatives = int(np.sum(~true_class & ~pred_class))
        total = hits + misses + false_alarms + correct_negatives
        expected_correct = (
            ((hits + misses) * (hits + false_alarms) + (correct_negatives + misses) * (correct_negatives + false_alarms)) / total
            if total
            else None
        )
        hss = (
            (hits + correct_negatives - expected_correct) / (total - expected_correct)
            if expected_correct is not None and total != expected_correct
            else None
        )
        hits_random = ((hits + misses) * (hits + false_alarms) / total) if total else None
        ets = (
            (hits - hits_random) / (hits + misses + false_alarms - hits_random)
            if hits_random is not None and (hits + misses + false_alarms - hits_random) != 0
            else None
        )
        return {
            "hits": hits,
            "misses": misses,
            "false_alarms": false_alarms,
            "correct_negatives": correct_negatives,
            "pod": hits / (hits + misses) if hits + misses else None,
            "far": false_alarms / (hits + false_alarms) if hits + false_alarms else None,
            "csi": hits / (hits + misses + false_alarms) if hits + misses + false_alarms else None,
            "hss": hss,
            "ets": ets,
            "accuracy": (hits + correct_negatives) / total if total else None,
            "bias_score": (hits + false_alarms) / (hits + misses) if hits + misses else None,
        }

    @staticmethod
    def rainfall_intensity_scores(
        y_true: Iterable[float],
        y_pred: Iterable[float],
        thresholds: Iterable[float] = (0.1, 2.0, 10.0, 30.0),
    ) -> dict[str, dict[str, float | int | None]]:
        return {f"threshold_{threshold:g}mm": WeatherMetrics.rainfall_scores(y_true, y_pred, threshold) for threshold in thresholds}

    @staticmethod
    def extreme_value_metrics(
        y_true: Iterable[float],
        y_pred: Iterable[float],
        percentile: float = 90,
    ) -> dict[str, float | int | None]:
        true, pred = WeatherMetrics._arrays(y_true, y_pred)
        cutoff = float(np.percentile(true, percentile))
        mask = true >= cutoff
        if not np.any(mask):
            return {
                "percentile": percentile,
                "threshold": cutoff,
                "extreme_threshold": cutoff,
                "count": 0,
                "extreme_count": 0,
                "mae": None,
                "rmse": None,
                "bias": None,
                "pod": None,
                "extreme_mae": None,
                "extreme_rmse": None,
                "extreme_capture_rate": None,
            }
        base = WeatherMetrics.regression_scores(true[mask], pred[mask])
        event = WeatherMetrics.rainfall_scores(true, pred, cutoff)
        pred_extreme = pred >= cutoff
        capture_rate = float(np.sum(mask & pred_extreme) / np.sum(mask))
        return {
            "percentile": percentile,
            "threshold": cutoff,
            "extreme_threshold": cutoff,
            "count": int(np.sum(mask)),
            "extreme_count": int(np.sum(mask)),
            "mae": base["mae"],
            "rmse": base["rmse"],
            "bias": base["bias"],
            "pod": event["pod"],
            "extreme_mae": base["mae"],
            "extreme_rmse": base["rmse"],
            "extreme_capture_rate": capture_rate,
        }
