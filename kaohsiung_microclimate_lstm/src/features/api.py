from __future__ import annotations

from typing import Any

import pandas as pd

from ..data.feature_engineering import (
    analyze_feature_importance,
    create_change_features,
    create_cyclic_time_features,
    create_interaction_features,
    create_lag_features,
    create_pressure_features,
    create_rolling_features,
    create_special_period_features,
    remove_highly_correlated_features,
    select_features_by_cumulative,
    select_features_by_importance,
)


class FeatureAPI:
    """Internal feature engineering API."""

    @staticmethod
    def create_features(df: pd.DataFrame, variable: str, config: dict[str, Any] | None = None) -> pd.DataFrame:
        config = config or {}
        variables = config.get("variables", [variable])
        out = df.copy()
        if "obs_time" in out.columns:
            out["obs_time"] = pd.to_datetime(out["obs_time"], errors="coerce")
            out = out.dropna(subset=["obs_time"]).set_index("obs_time").sort_index()
        out = create_lag_features(out, variables, config.get("lag_hours", [0.5, 1, 2, 3, 6]))
        out = create_rolling_features(out, variables, config.get("rolling_windows_hours", {"1h": 1, "3h": 3, "6h": 6}))
        out = create_change_features(out, config.get("change_variables", [v for v in variables if v in out.columns]), config.get("change_hours", [0.5, 1, 3, 6]))
        if isinstance(out.index, pd.DatetimeIndex):
            out = create_cyclic_time_features(out)
            out = create_special_period_features(out)
        if "pressure" in out.columns:
            out = create_pressure_features(out)
        out = create_interaction_features(out)
        return out

    @staticmethod
    def select_features(
        X: pd.DataFrame,
        y: Any | None = None,
        method: str = "correlation",
        threshold: float = 0.95,
        model: Any | None = None,
    ) -> list[str]:
        if method == "correlation":
            return remove_highly_correlated_features(X, threshold=threshold)
        if method == "importance":
            if model is None:
                raise ValueError("model is required for importance-based selection")
            importance = analyze_feature_importance(model, X.columns)
            return select_features_by_importance(importance, threshold=threshold)
        if method == "cumulative":
            if model is None:
                raise ValueError("model is required for cumulative importance selection")
            importance = analyze_feature_importance(model, X.columns)
            return select_features_by_cumulative(importance, cumulative_threshold=threshold)
        raise ValueError(f"Unsupported feature selection method: {method}")
