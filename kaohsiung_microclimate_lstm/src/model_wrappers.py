from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .evaluation.metrics import WeatherMetrics


class BaseWeatherModel:
    """Common save/load/evaluate contract for tabular weather models."""

    target_variable = "target"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.model: Any = None
        self.feature_names: list[str] | None = None

    def train(self, X: pd.DataFrame, y: Any, X_val: pd.DataFrame | None = None, y_val: Any | None = None) -> Any:
        if self.model is None:
            raise RuntimeError("model is not initialized")
        self.feature_names = list(X.columns)
        self.model.fit(X, y)
        return self.model

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model is not initialized")
        return np.asarray(self.model.predict(X), dtype=float)

    def evaluate(self, X: pd.DataFrame, y: Any) -> dict[str, Any]:
        pred = self.predict(X)
        return WeatherMetrics.regression_scores(y, pred)

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "class": self.__class__.__name__,
                "target_variable": self.target_variable,
                "config": self.config,
                "feature_names": self.feature_names,
                "model": self.model,
            },
            out,
        )
        return out

    def load(self, path: str | Path) -> "BaseWeatherModel":
        payload = joblib.load(path)
        self.config = payload.get("config", {})
        self.feature_names = payload.get("feature_names")
        self.model = payload["model"]
        return self


class RainfallModel(BaseWeatherModel):
    target_variable = "precipitation_1hr"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.algorithm = self.config.get("primary_algorithm", "random_forest")
        self.model = _build_regressor(self.algorithm, self.config)

    def train(self, X: pd.DataFrame, y: Any, X_val: pd.DataFrame | None = None, y_val: Any | None = None) -> Any:
        self.feature_names = list(X.columns)
        sample_weight = self._sample_weights(np.asarray(y, dtype=float)) if self.config.get("preprocessing", {}).get("handle_imbalance", False) else None
        try:
            self.model.fit(X, y, sample_weight=sample_weight)
        except TypeError:
            self.model.fit(X, y)
        return self.model

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = super().predict(X)
        post = self.config.get("postprocessing", {})
        if post.get("clip_negative", True):
            pred = np.clip(pred, float(post.get("min_value", 0.0)), float(post.get("max_value", 200.0)))
        if post.get("smooth_small_values", False):
            pred[pred < float(post.get("smooth_threshold", 0.5))] = 0.0
        return pred

    def evaluate(self, X: pd.DataFrame, y: Any) -> dict[str, Any]:
        pred = self.predict(X)
        metrics = WeatherMetrics.regression_scores(y, pred)
        metrics["rainfall"] = WeatherMetrics.rainfall_scores(y, pred, threshold=float(self.config.get("rain_threshold", 0.1)))
        return metrics

    def _sample_weights(self, y: np.ndarray) -> np.ndarray:
        threshold = float(self.config.get("preprocessing", {}).get("zero_threshold", 0.1))
        weights = np.ones(len(y), dtype=float)
        rain = y >= threshold
        n_rain = int(rain.sum())
        n_no_rain = int((~rain).sum())
        if n_rain and n_no_rain:
            weights[rain] = n_no_rain / n_rain
        return weights


class RainfallCascadeModel(BaseWeatherModel):
    target_variable = "precipitation_1hr"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        from sklearn.ensemble import RandomForestClassifier

        self.threshold = float(self.config.get("rain_threshold", 0.1))
        self.classifier = RandomForestClassifier(**self.config.get("classifier", {"n_estimators": 50, "random_state": 42}))
        self.regressor = _build_regressor(self.config.get("regressor_algorithm", "random_forest"), self.config.get("regressor", {}))

    def train(self, X: pd.DataFrame, y: Any, X_val: pd.DataFrame | None = None, y_val: Any | None = None) -> Any:
        y_arr = np.asarray(y, dtype=float)
        self.feature_names = list(X.columns)
        y_class = y_arr >= self.threshold
        self.classifier.fit(X, y_class)
        if y_class.any():
            self.regressor.fit(X.loc[y_class], y_arr[y_class])
        else:
            self.regressor.fit(X, y_arr)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        rain = self.classifier.predict(X).astype(bool)
        pred = np.zeros(len(X), dtype=float)
        if rain.any():
            pred[rain] = np.asarray(self.regressor.predict(X.loc[rain]), dtype=float)
        return np.clip(pred, 0.0, float(self.config.get("max_value", 200.0)))


class WindModel(BaseWeatherModel):
    target_variable = "wind_speed"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.model = _build_regressor(self.config.get("primary_algorithm", "random_forest"), self.config)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = super().predict(X)
        post = self.config.get("postprocessing", {})
        return np.clip(pred, float(post.get("min_value", 0.0)), float(post.get("max_value", 50.0)))


class GustModel(BaseWeatherModel):
    target_variable = "wind_gust"

    def __init__(self, config: dict[str, Any] | None = None, wind_model: WindModel | None = None) -> None:
        super().__init__(config)
        self.wind_model = wind_model
        self.model = _build_regressor(self.config.get("primary_algorithm", "random_forest"), self.config)

    def predict(self, X: pd.DataFrame, wind_speed_pred: Any | None = None) -> np.ndarray:  # type: ignore[override]
        pred = super().predict(X)
        post = self.config.get("postprocessing", {})
        pred = np.clip(pred, float(post.get("min_value", 0.0)), float(post.get("max_value", 60.0)))
        if post.get("enforce_gust_ge_wind", True):
            if wind_speed_pred is None and self.wind_model is not None:
                wind_speed_pred = self.wind_model.predict(X)
            if wind_speed_pred is not None:
                pred = np.maximum(pred, np.asarray(wind_speed_pred, dtype=float))
        return pred


class VisibilityModel(BaseWeatherModel):
    target_variable = "visibility"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.model = _build_regressor(self.config.get("primary_algorithm", "random_forest"), self.config)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = super().predict(X)
        post = self.config.get("postprocessing", {})
        return np.clip(pred, float(post.get("min_value", 0.0)), float(post.get("max_value", 30000.0)))

    def predict_grade(self, X: pd.DataFrame) -> np.ndarray:
        values = self.predict(X)
        grades = self.config.get(
            "postprocessing",
            {},
        ).get("visibility_grades", {"excellent": 10000, "good": 5000, "moderate": 1000, "poor": 500, "very_poor": 0})
        labels = []
        for value in values:
            if value >= grades["excellent"]:
                labels.append("excellent")
            elif value >= grades["good"]:
                labels.append("good")
            elif value >= grades["moderate"]:
                labels.append("moderate")
            elif value >= grades["poor"]:
                labels.append("poor")
            else:
                labels.append("very_poor")
        return np.asarray(labels, dtype=object)


class EnsembleModel(BaseWeatherModel):
    target_variable = "ensemble_target"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.model = self._build_stacking()

    def _build_stacking(self) -> Any:
        from sklearn.ensemble import RandomForestRegressor, StackingRegressor
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import KFold

        estimators = [
            ("random_forest", RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)),
            ("gradient_boosting", _build_regressor("gradient_boosting", {"gradient_boosting": {"random_state": 42}})),
        ]
        cv_splits = int(self.config.get("stacking", {}).get("cv_splits", 5))
        return StackingRegressor(estimators=estimators, final_estimator=Ridge(alpha=1.0), cv=KFold(n_splits=cv_splits, shuffle=False), n_jobs=None)


def _build_regressor(algorithm: str, config: dict[str, Any]) -> Any:
    algorithm = algorithm.lower()
    if algorithm == "xgboost":
        try:
            from xgboost import XGBRegressor

            return XGBRegressor(**config.get("xgboost", {}))
        except Exception:
            algorithm = "gradient_boosting"
    if algorithm == "lightgbm":
        try:
            from lightgbm import LGBMRegressor

            return LGBMRegressor(**config.get("lightgbm", {}))
        except Exception:
            algorithm = "gradient_boosting"
    if algorithm == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(**config.get("gradient_boosting", {"random_state": 42}))
    from sklearn.ensemble import RandomForestRegressor

    return RandomForestRegressor(**config.get("random_forest", {"n_estimators": 100, "random_state": 42, "n_jobs": -1}))


def benchmark_regressors(
    X_train: pd.DataFrame,
    y_train: Any,
    X_test: pd.DataFrame,
    y_test: Any,
    config: dict[str, Any] | None = None,
    algorithms: list[str] | None = None,
) -> dict[str, Any]:
    """Train comparable tabular regressors and return regression metrics."""
    cfg = config or {}
    selected = algorithms or cfg.get("algorithms") or ["random_forest", "lightgbm", "xgboost"]
    results: dict[str, Any] = {}
    for algorithm in selected:
        model = _build_regressor(str(algorithm), cfg)
        actual_algorithm = model.__class__.__name__
        model.fit(X_train, y_train)
        pred = np.asarray(model.predict(X_test), dtype=float)
        results[str(algorithm)] = {
            "requested_algorithm": str(algorithm),
            "actual_estimator": actual_algorithm,
            "metrics": WeatherMetrics.regression_scores(y_test, pred),
        }
    return results
