from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_HORIZONS = {"H1": 30, "H2": 60, "H3": 90, "H4": 120}


def build_port_local_training_dataset(
    khwd_station_frames: dict[str, pd.DataFrame],
    target_definition: dict | None,
    config: dict,
) -> dict[str, Any]:
    """
    Build a supervised H1-H4 dataset from KHWD port-local wind station frames.
    """
    target_definition = target_definition or {}
    horizons = _forecast_horizons(config)
    tolerance_minutes = int(
        config.get("port_local_training", {})
        .get("label_alignment", {})
        .get("tolerance_minutes", 30)
    )
    rows = _normalize_station_rows(khwd_station_frames)
    if rows.empty:
        dataset = pd.DataFrame()
        return {
            "dataset": dataset,
            "feature_columns": [],
            "label_columns": [],
            "horizons": horizons,
            "dataset_report": _dataset_report(dataset, [], [], horizons, tolerance_minutes, ["No KHWD station rows available."]),
        }

    aggregate = _aggregate_by_time(rows)
    aggregate = _add_temporal_features(aggregate)
    aggregate = _add_lag_rolling_features(aggregate)
    dataset, label_columns = _add_labels(aggregate, horizons, tolerance_minutes)
    rain_labels = _add_optional_rain_labels(dataset, horizons, tolerance_minutes, bool(target_definition.get("train_rain", False)))
    label_columns.extend(rain_labels)
    feature_columns = [col for col in dataset.columns if col not in {"obs_time", *label_columns}]
    report = _dataset_report(dataset, feature_columns, label_columns, horizons, tolerance_minutes, [])
    return {
        "dataset": dataset,
        "feature_columns": feature_columns,
        "label_columns": label_columns,
        "horizons": horizons,
        "dataset_report": report,
    }


def _normalize_station_rows(khwd_station_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for station_id, frame in khwd_station_frames.items():
        if frame is None or frame.empty:
            continue
        work = frame.copy()
        if "obs_time" not in work.columns and "timestamp" in work.columns:
            work["obs_time"] = work["timestamp"]
        if "obs_time" not in work.columns:
            continue
        work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
        work = work.dropna(subset=["obs_time"]).copy()
        if work.empty:
            continue
        if work["obs_time"].dt.tz is None:
            work["obs_time"] = work["obs_time"].dt.tz_localize(TAIPEI)
        else:
            work["obs_time"] = work["obs_time"].dt.tz_convert(TAIPEI)
        work["station_id"] = str(station_id)
        for column in ["wind_speed", "wind_gust", "wind_direction", "wind_gust_direction", "precipitation_1hr", "precip_1hr"]:
            if column in work.columns:
                work[column] = pd.to_numeric(work[column], errors="coerce")
        rows.append(
            work[
                [
                    col
                    for col in [
                        "obs_time",
                        "station_id",
                        "wind_speed",
                        "wind_gust",
                        "wind_direction",
                        "wind_gust_direction",
                        "precipitation_1hr",
                        "precip_1hr",
                    ]
                    if col in work.columns
                ]
            ]
        )
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["obs_time", "station_id"])


def _aggregate_by_time(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = rows.groupby("obs_time", sort=True)
    out = pd.DataFrame(index=grouped.size().index)
    wind = grouped["wind_speed"] if "wind_speed" in rows.columns else None
    gust = grouped["wind_gust"] if "wind_gust" in rows.columns else None
    if wind is not None:
        out["khwd_wind_speed_mean"] = wind.mean()
        out["khwd_wind_speed_max"] = wind.max()
        out["khwd_wind_speed_min"] = wind.min()
        out["khwd_wind_speed_std"] = wind.std(ddof=0).fillna(0.0)
    if gust is not None:
        out["khwd_wind_gust_mean"] = gust.mean()
        out["khwd_wind_gust_max"] = gust.max()
        out["khwd_wind_gust_min"] = gust.min()
        out["khwd_wind_gust_std"] = gust.std(ddof=0).fillna(0.0)
    out["khwd_station_count"] = grouped["station_id"].nunique()
    out["khwd_valid_wind_station_count"] = grouped["wind_speed"].count() if "wind_speed" in rows.columns else 0
    out["khwd_valid_gust_station_count"] = grouped["wind_gust"].count() if "wind_gust" in rows.columns else 0
    out["khwd_wind_speed_range"] = out.get("khwd_wind_speed_max", np.nan) - out.get("khwd_wind_speed_min", np.nan)
    out["khwd_wind_gust_range"] = out.get("khwd_wind_gust_max", np.nan) - out.get("khwd_wind_gust_min", np.nan)
    out["khwd_wind_direction_sin_mean"] = _direction_component_mean(rows, "wind_direction", np.sin)
    out["khwd_wind_direction_cos_mean"] = _direction_component_mean(rows, "wind_direction", np.cos)
    out["khwd_gust_direction_sin_mean"] = _direction_component_mean(rows, "wind_gust_direction", np.sin)
    out["khwd_gust_direction_cos_mean"] = _direction_component_mean(rows, "wind_gust_direction", np.cos)
    if "precipitation_1hr" in rows.columns or "precip_1hr" in rows.columns:
        precip_col = "precipitation_1hr" if "precipitation_1hr" in rows.columns else "precip_1hr"
        precip = grouped[precip_col]
        out["port_local_precipitation_1hr_max"] = precip.max()
        out["port_local_precipitation_1hr_mean"] = precip.mean()
        out["port_local_rainy_station_count"] = precip.apply(lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5).sum()))
        out["port_local_rainy_station_ratio"] = out["port_local_rainy_station_count"] / out["khwd_station_count"].replace(0, np.nan)
    out = out.reset_index().rename(columns={"index": "obs_time"})
    return out


def _direction_component_mean(rows: pd.DataFrame, column: str, fn) -> pd.Series:
    if column not in rows.columns:
        return pd.Series(dtype=float)
    work = rows[["obs_time", column]].copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    radians = np.deg2rad(work[column])
    work["component"] = fn(radians)
    return work.groupby("obs_time")["component"].mean()


def _add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    times = pd.to_datetime(out["obs_time"], errors="coerce")
    hour = times.dt.hour + times.dt.minute / 60.0
    doy = times.dt.dayofyear
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 366.0)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 366.0)
    return out


def _add_lag_rolling_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("obs_time").reset_index(drop=True).copy()
    for column, lags in {
        "khwd_wind_speed_mean": [1, 2],
        "khwd_wind_speed_max": [1],
        "khwd_wind_gust_max": [1, 2],
    }.items():
        if column in out.columns:
            for lag in lags:
                out[f"{column}_lag{lag}"] = out[column].shift(lag)
    for column in ["khwd_wind_speed_mean", "khwd_wind_speed_max", "khwd_wind_gust_mean", "khwd_wind_gust_max"]:
        if column in out.columns:
            out[f"{column}_roll3"] = out[column].rolling(3, min_periods=1).mean()
    return out


def _add_labels(frame: pd.DataFrame, horizons: dict[str, int], tolerance_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    out = frame.sort_values("obs_time").reset_index(drop=True).copy()
    label_columns: list[str] = []
    times = pd.to_datetime(out["obs_time"], errors="coerce")
    if times.dt.tz is None:
        times = times.dt.tz_localize(TAIPEI)
    index = pd.DatetimeIndex(times)
    source = out.set_index(index)
    tolerance = pd.Timedelta(minutes=tolerance_minutes)
    for horizon, minutes in horizons.items():
        target_times = index + pd.Timedelta(minutes=int(minutes))
        indexer = index.get_indexer(target_times, method="nearest", tolerance=tolerance)
        speed_label = f"target_wind_speed_{horizon}"
        gust_label = f"target_wind_gust_{horizon}"
        out[speed_label] = _values_by_indexer(source, "khwd_wind_speed_max", indexer)
        out[gust_label] = _values_by_indexer(source, "khwd_wind_gust_max", indexer)
        label_columns.extend([speed_label, gust_label])
    return out, label_columns


def _add_optional_rain_labels(frame: pd.DataFrame, horizons: dict[str, int], tolerance_minutes: int, enabled: bool) -> list[str]:
    if not enabled or "port_local_precipitation_1hr_max" not in frame.columns:
        return []
    labels: list[str] = []
    times = pd.to_datetime(frame["obs_time"], errors="coerce")
    index = pd.DatetimeIndex(times)
    source = frame.set_index(index)
    tolerance = pd.Timedelta(minutes=tolerance_minutes)
    for horizon, minutes in horizons.items():
        indexer = index.get_indexer(index + pd.Timedelta(minutes=int(minutes)), method="nearest", tolerance=tolerance)
        col = f"target_rain_event_{horizon}"
        frame[col] = [None if pos < 0 else int(float(source.iloc[pos]["port_local_precipitation_1hr_max"]) > 0.5) for pos in indexer]
        labels.append(col)
    return labels


def _values_by_indexer(source: pd.DataFrame, column: str, indexer: np.ndarray) -> list[float | None]:
    if column not in source.columns:
        return [None for _ in indexer]
    values = source[column].to_numpy()
    return [None if pos < 0 else float(values[pos]) if pd.notna(values[pos]) else None for pos in indexer]


def _forecast_horizons(config: dict) -> dict[str, int]:
    anchors = config.get("forecast", {}).get("anchors")
    if isinstance(anchors, dict) and anchors:
        return {str(key): int(value) for key, value in anchors.items()}
    offsets = config.get("anchor_offsets_minutes")
    if offsets:
        return {f"H{idx + 1}": int(value) for idx, value in enumerate(offsets)}
    return dict(DEFAULT_HORIZONS)


def _dataset_report(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    label_columns: list[str],
    horizons: dict[str, int],
    tolerance_minutes: int,
    warnings: list[str],
) -> dict[str, Any]:
    if dataset.empty or "obs_time" not in dataset.columns:
        time_start = None
        time_end = None
    else:
        times = pd.to_datetime(dataset["obs_time"], errors="coerce")
        time_start = None if times.isna().all() else times.min().isoformat()
        time_end = None if times.isna().all() else times.max().isoformat()
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "sample_count": int(len(dataset)),
        "time_start": time_start,
        "time_end": time_end,
        "feature_columns": feature_columns,
        "label_columns": label_columns,
        "horizons": horizons,
        "label_alignment_method": "nearest_with_tolerance",
        "tolerance_minutes": tolerance_minutes,
        "warnings": warnings,
    }
