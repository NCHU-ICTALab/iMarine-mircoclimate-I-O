from __future__ import annotations

from typing import Any

import pandas as pd


def _last_numeric(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or frame.empty:
        return None
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(series.iloc[-1]) if len(series) else None


def build_multistation_features(target_observations: pd.DataFrame, nearby_observations: pd.DataFrame | None, config: dict[str, Any]) -> dict[str, Any]:
    forbidden = set(config.get("features", {}).get("forbidden_if_not_historical", []))
    features: dict[str, Any] = {}
    for column in config.get("features", {}).get("target_station", []):
        if column in forbidden:
            continue
        value = _last_numeric(target_observations, column)
        if value is not None:
            features[column] = value

    agg_cfg = config.get("features", {}).get("nearby_station_aggregation", {})
    if not agg_cfg.get("enabled", True) or nearby_observations is None or nearby_observations.empty:
        features["nearby_active_station_count"] = 0
        return features

    variables = agg_cfg.get("variables", ["wind_speed", "wind_gust", "precipitation_1hr"])
    for variable in variables:
        if variable in forbidden:
            continue
        if variable not in nearby_observations.columns:
            continue
        values = pd.to_numeric(nearby_observations[variable], errors="coerce").dropna()
        if values.empty:
            continue
        features[f"nearby_{variable}_mean"] = float(values.mean())
        features[f"nearby_{variable}_max"] = float(values.max())
        features[f"nearby_{variable}_min"] = float(values.min())
        features[f"nearby_{variable}_std"] = float(values.std(ddof=0))
    features["nearby_active_station_count"] = int(len(nearby_observations))
    if "precipitation_1hr" in nearby_observations.columns:
        rain = pd.to_numeric(nearby_observations["precipitation_1hr"], errors="coerce").fillna(0.0)
        features["nearby_rain_station_count"] = int((rain > 0).sum())
    return features
