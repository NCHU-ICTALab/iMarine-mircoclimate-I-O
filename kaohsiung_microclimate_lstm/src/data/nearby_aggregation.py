from __future__ import annotations

from typing import Any

import pandas as pd


def _latest_row(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if "obs_time" in frame.columns:
        work = frame.copy()
        work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
        work = work.sort_values("obs_time")
        return work.iloc[-1]
    return frame.iloc[-1]


def _numeric_value(row: pd.Series, column: str) -> float | None:
    if column not in row:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    series = pd.Series(values, dtype=float)
    return {
        "mean": float(series.mean()),
        "max": float(series.max()),
        "min": float(series.min()),
        "std": float(series.std(ddof=0)),
    }


def build_nearby_aggregated_features(
    station_frames: dict[str, pd.DataFrame],
    target_station_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    target = str(target_station_id)
    target_row = _latest_row(station_frames[target]) if target in station_frames else pd.Series(dtype=float)
    nearby_station_ids = [station_id for station_id in station_frames if station_id != target]
    latest_by_station = {station_id: _latest_row(frame) for station_id, frame in station_frames.items() if station_id != target}
    features: dict[str, float | int] = {}
    missing_features: list[str] = []

    for variable in ("wind_speed", "wind_gust"):
        values = [
            value
            for value in (_numeric_value(row, variable) for row in latest_by_station.values())
            if value is not None
        ]
        stats = _stats(values)
        for name, value in stats.items():
            features[f"nearby_{variable}_{name}"] = value
        target_value = _numeric_value(target_row, variable)
        if target_value is not None and "mean" in stats:
            features[f"target_{variable}_minus_nearby_mean"] = target_value - stats["mean"]
        if target_value is not None and "max" in stats:
            features[f"nearby_{variable}_max_minus_target"] = stats["max"] - target_value
        if not stats:
            missing_features.append(variable)

    rain_values = [
        value
        for value in (_numeric_value(row, "precipitation_1hr") for row in latest_by_station.values())
        if value is not None
    ]
    if rain_values:
        rain = pd.Series(rain_values, dtype=float)
        features["nearby_precipitation_1hr_mean"] = float(rain.mean())
        features["nearby_precipitation_1hr_max"] = float(rain.max())
        features["nearby_precipitation_1hr_sum"] = float(rain.sum())
        features["nearby_rainy_station_count"] = int((rain > 0).sum())
        features["nearby_rainy_station_ratio"] = float((rain > 0).mean())
    else:
        missing_features.append("precipitation_1hr")

    features["input_station_count"] = int(len(station_frames))
    features["nearby_station_count"] = int(len(nearby_station_ids))
    features["available_wind_station_count"] = int(sum(_numeric_value(row, "wind_speed") is not None for row in latest_by_station.values()))
    features["available_gust_station_count"] = int(sum(_numeric_value(row, "wind_gust") is not None for row in latest_by_station.values()))
    features["available_rain_station_count"] = int(sum(_numeric_value(row, "precipitation_1hr") is not None for row in latest_by_station.values()))
    features["multi_station_input_flag"] = 1 if nearby_station_ids else 0
    features["fallback_to_single_station_flag"] = 0 if nearby_station_ids else 1

    return {
        "features": pd.DataFrame([features]),
        "feature_names": list(features),
        "nearby_station_ids_used": nearby_station_ids,
        "nearby_station_count": len(nearby_station_ids),
        "aggregation_status": "ok" if nearby_station_ids else "single_station_fallback",
        "missing_features": missing_features,
    }
