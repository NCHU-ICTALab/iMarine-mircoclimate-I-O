from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd


def _steps_per_hour(index: pd.Index, default: int = 2) -> int:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return default
    diffs = index.to_series().diff().dropna().dt.total_seconds() / 60
    if diffs.empty:
        return default
    minutes = float(diffs.median())
    return max(1, int(round(60 / minutes))) if minutes > 0 else default


def _step_count(hours: float, index: pd.Index) -> int:
    return max(1, int(round(float(hours) * _steps_per_hour(index))))


def create_lag_features(
    df: pd.DataFrame,
    variables: Iterable[str],
    lags_hours: Iterable[float] = (0.5, 1, 2, 3, 6),
) -> pd.DataFrame:
    out = df.copy()
    for variable in variables:
        if variable not in out:
            continue
        for lag_hours in lags_hours:
            suffix = f"{lag_hours:g}h"
            out[f"{variable}_lag_{suffix}"] = out[variable].shift(_step_count(lag_hours, out.index))
    return out


def create_rolling_features(
    df: pd.DataFrame,
    variables: Iterable[str],
    windows_hours: dict[str, float] | None = None,
    statistics: Iterable[str] = ("mean", "max", "min", "std", "sum"),
) -> pd.DataFrame:
    out = df.copy()
    windows = windows_hours or {"1h": 1, "3h": 3, "6h": 6}
    for variable in variables:
        if variable not in out:
            continue
        for window_name, hours in windows.items():
            rolling = out[variable].rolling(_step_count(hours, out.index), min_periods=1)
            for stat in statistics:
                name = f"{variable}_roll_{window_name}_{stat}"
                if stat == "mean":
                    out[name] = rolling.mean()
                elif stat == "max":
                    out[name] = rolling.max()
                elif stat == "min":
                    out[name] = rolling.min()
                elif stat == "std":
                    out[name] = rolling.std(ddof=0)
                elif stat == "sum":
                    out[name] = rolling.sum()
    return out


def create_change_features(
    df: pd.DataFrame,
    variables: Iterable[str],
    change_hours: Iterable[float] = (0.5, 1, 3, 6),
    trend_hours: float = 3,
) -> pd.DataFrame:
    out = df.copy()
    trend_steps = _step_count(trend_hours, out.index)
    for variable in variables:
        if variable not in out:
            continue
        for hours in change_hours:
            suffix = f"{hours:g}h"
            out[f"{variable}_change_{suffix}"] = out[variable].diff(_step_count(hours, out.index))
        out[f"{variable}_trend_{trend_hours:g}h"] = out[variable].rolling(trend_steps).apply(_linear_slope, raw=True)
    return out


def create_cyclic_time_features(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("create_cyclic_time_features requires a DatetimeIndex")
    out = df.copy()
    hour = out.index.hour + out.index.minute / 60
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    doy = out.index.dayofyear
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365)
    month = out.index.month
    out["month_sin"] = np.sin(2 * np.pi * month / 12)
    out["month_cos"] = np.cos(2 * np.pi * month / 12)
    return out


def create_special_period_features(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("create_special_period_features requires a DatetimeIndex")
    out = df.copy()
    out["is_night"] = ((out.index.hour >= 18) | (out.index.hour < 6)).astype(int)
    out["is_dawn"] = ((out.index.hour >= 4) & (out.index.hour < 8)).astype(int)
    out["is_afternoon"] = ((out.index.hour >= 13) & (out.index.hour < 17)).astype(int)
    out["is_typhoon_season"] = ((out.index.month >= 5) & (out.index.month <= 11)).astype(int)
    return out


def create_pressure_features(df: pd.DataFrame, pressure_col: str = "pressure") -> pd.DataFrame:
    out = df.copy()
    if pressure_col not in out:
        return out
    out["pressure_current"] = out[pressure_col]
    out = create_change_features(out, [pressure_col], (0.5, 1, 3, 6), trend_hours=3)
    out["pressure_change_0.5h"] = out[f"{pressure_col}_change_0.5h"]
    out["pressure_change_1h"] = out[f"{pressure_col}_change_1h"]
    out["pressure_change_3h"] = out[f"{pressure_col}_change_3h"]
    out["pressure_change_6h"] = out[f"{pressure_col}_change_6h"]
    out["pressure_trend_3h"] = out[f"{pressure_col}_trend_3h"]
    out["pressure_acceleration_1h"] = out["pressure_change_1h"].diff(_step_count(1, out.index))
    out["pressure_anomaly"] = out[pressure_col] - out[pressure_col].rolling(_step_count(24 * 30, out.index), min_periods=1).mean()
    return out


def create_temperature_dewpoint_features(
    df: pd.DataFrame,
    temperature_col: str = "temperature",
    dewpoint_col: str = "dewpoint",
) -> pd.DataFrame:
    out = df.copy()
    if temperature_col not in out or dewpoint_col not in out:
        return out
    out["temperature_current"] = out[temperature_col]
    out["dewpoint_current"] = out[dewpoint_col]
    out["temp_dewpoint_diff"] = out[temperature_col] - out[dewpoint_col]
    for hours in (1, 2, 6):
        out[f"temp_dewpoint_diff_lag_{hours:g}h"] = out["temp_dewpoint_diff"].shift(_step_count(hours, out.index))
    out["temp_change_1h"] = out[temperature_col].diff(_step_count(1, out.index))
    out["dewpoint_change_1h"] = out[dewpoint_col].diff(_step_count(1, out.index))
    out["saturation_ratio"] = np.exp(-0.06 * out["temp_dewpoint_diff"])
    return out


def create_humidity_features(df: pd.DataFrame, humidity_col: str = "humidity") -> pd.DataFrame:
    out = df.copy()
    if humidity_col not in out:
        return out
    out["humidity_current"] = out[humidity_col]
    out["humidity_change_1h"] = out[humidity_col].diff(_step_count(1, out.index))
    out["humidity_change_3h"] = out[humidity_col].diff(_step_count(3, out.index))
    out["humidity_roll_3h_mean"] = out[humidity_col].rolling(_step_count(3, out.index), min_periods=1).mean()
    out["high_humidity_hours"] = (out[humidity_col] > 85).rolling(_step_count(6, out.index), min_periods=1).sum() / _steps_per_hour(out.index)
    return out


def create_wind_features(
    df: pd.DataFrame,
    wind_speed_col: str = "wind_speed",
    wind_direction_col: str = "wind_direction",
) -> pd.DataFrame:
    out = df.copy()
    if wind_speed_col not in out or wind_direction_col not in out:
        return out
    out["wind_u"] = -out[wind_speed_col] * np.sin(np.radians(out[wind_direction_col]))
    out["wind_v"] = -out[wind_speed_col] * np.cos(np.radians(out[wind_direction_col]))
    for hours in (1, 2, 6):
        out[f"wind_u_lag_{hours:g}h"] = out["wind_u"].shift(_step_count(hours, out.index))
        out[f"wind_v_lag_{hours:g}h"] = out["wind_v"].shift(_step_count(hours, out.index))
    out["wind_speed_change_1h"] = out[wind_speed_col].diff(_step_count(1, out.index))
    direction_change = out[wind_direction_col].diff(_step_count(1, out.index))
    out["wind_direction_change_1h"] = ((direction_change + 180) % 360) - 180
    out["wind_speed_std_1h"] = out[wind_speed_col].rolling(_step_count(1, out.index), min_periods=1).std(ddof=0)
    out["wind_speed_std_3h"] = out[wind_speed_col].rolling(_step_count(3, out.index), min_periods=1).std(ddof=0)
    return out


def create_spatial_aggregation_features(
    primary: pd.DataFrame,
    neighbors: dict[str, pd.DataFrame],
    variables: Iterable[str],
) -> pd.DataFrame:
    out = primary.copy()
    for variable in variables:
        series = [frame[variable].rename(station_id) for station_id, frame in neighbors.items() if variable in frame]
        if not series:
            continue
        values = pd.concat(series, axis=1)
        out[f"{variable}_neighbors_mean"] = values.mean(axis=1)
        out[f"{variable}_neighbors_max"] = values.max(axis=1)
        out[f"{variable}_neighbors_min"] = values.min(axis=1)
        out[f"{variable}_neighbors_std"] = values.std(axis=1, ddof=0)
        if variable in out:
            out[f"{variable}_spatial_diff"] = out[variable] - out[f"{variable}_neighbors_mean"]
    return out


def create_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "pressure_change_3h" in out and "humidity" in out:
        out["pressure_humidity_interaction"] = out["pressure_change_3h"] * out["humidity"] / 100
    if "temp_dewpoint_diff" in out and "wind_speed" in out:
        out["dewpoint_wind_interaction"] = out["temp_dewpoint_diff"] / (out["wind_speed"] + 0.1)
    if "pressure_change_1h" in out and "temp_change_1h" in out:
        out["pressure_temp_interaction"] = out["pressure_change_1h"] * out["temp_change_1h"]
    return out


def analyze_feature_importance(model: Any, feature_names: Iterable[str]) -> pd.DataFrame:
    if not hasattr(model, "feature_importances_"):
        raise ValueError("model must expose feature_importances_")
    importance = np.asarray(model.feature_importances_, dtype=float)
    names = list(feature_names)
    if len(names) != len(importance):
        raise ValueError("feature_names length must match feature_importances_")
    frame = pd.DataFrame({"feature": names, "importance": importance}).sort_values("importance", ascending=False)
    total = float(frame["importance"].sum())
    frame["normalized_importance"] = frame["importance"] / total if total > 0 else 0.0
    frame["cumulative_importance"] = frame["normalized_importance"].cumsum()
    return frame.reset_index(drop=True)


def select_features_by_importance(importance_df: pd.DataFrame, threshold: float = 0.001) -> list[str]:
    return importance_df.loc[importance_df["importance"] >= threshold, "feature"].astype(str).tolist()


def select_features_by_cumulative(importance_df: pd.DataFrame, cumulative_threshold: float = 0.95) -> list[str]:
    selected = importance_df.loc[importance_df["cumulative_importance"] <= cumulative_threshold, "feature"].astype(str).tolist()
    if not selected and not importance_df.empty:
        selected = [str(importance_df.iloc[0]["feature"])]
    return selected


def remove_highly_correlated_features(df: pd.DataFrame, threshold: float = 0.95) -> list[str]:
    corr = df.corr(numeric_only=True).abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    drop = {column for column in upper.columns if any(upper[column] > threshold)}
    return [column for column in df.columns if column not in drop]


def _linear_slope(values: np.ndarray) -> float:
    if len(values) < 2 or np.any(~np.isfinite(values)):
        return np.nan
    return float(np.polyfit(np.arange(len(values)), values, 1)[0])
