from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from .upstream_lead_features import build_upstream_lead_features, load_zoning_config


TAIPEI = timezone(timedelta(hours=8))


def build_nearby_historical_training_dataset(
    station_frames: dict[str, pd.DataFrame],
    station_ranking: dict,
    config: dict,
) -> dict[str, Any]:
    selected = list(station_ranking.get("selected_station_ids", []))
    distance_map = {str(item["station_id"]): float(item.get("distance_to_port_km", 0.0)) for item in station_ranking.get("ranked_stations", [])}
    rows = []
    for station_id in selected:
        frame = station_frames.get(station_id)
        if frame is None or frame.empty:
            continue
        work = frame.copy()
        work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
        work = work.dropna(subset=["obs_time"]).copy()
        work["station_id"] = str(station_id)
        work["distance_to_port_km"] = distance_map.get(str(station_id), np.nan)
        rows.append(work)
    if not rows:
        dataset = pd.DataFrame()
        return {
            "dataset": dataset,
            "feature_columns": [],
            "label_columns": [],
            "selected_station_ids": selected,
            "dataset_report": _report(dataset, selected, [], []),
        }
    raw = pd.concat(rows, ignore_index=True).sort_values(["obs_time", "station_id"])
    training_cfg = config.get("nearby_cwa_historical_training", {})
    aggregate = _aggregate(
        raw,
        enable_pressure_humidity_features=bool(training_cfg.get("enable_pressure_humidity_features", False)),
    )
    enable_upstream_features = bool(
        training_cfg.get("enable_upstream_lead_features", False)
    )
    if enable_upstream_features:
        zoning = load_zoning_config(config.get("zoning_config_path"))
        if zoning:
            upstream = build_upstream_lead_features(raw, zoning, selected)
            aggregate = aggregate.merge(upstream, on="obs_time", how="left")
    aggregate = _add_time_features(aggregate)
    aggregate = _add_lag_roll(aggregate)
    dataset, labels = _add_labels(aggregate, _horizons(config))
    features = [col for col in dataset.columns if col not in {"obs_time", *labels}]
    return {
        "dataset": dataset,
        "feature_columns": features,
        "label_columns": labels,
        "selected_station_ids": selected,
        "dataset_report": _report(dataset, selected, features, labels),
    }


def _aggregate(raw: pd.DataFrame, enable_pressure_humidity_features: bool = False) -> pd.DataFrame:
    grouped = raw.groupby("obs_time", sort=True)
    out = pd.DataFrame(index=grouped.size().index)
    out["nearby_cwa_station_count"] = grouped["station_id"].nunique()
    for src, prefix in [("wind_speed", "nearby_cwa_wind_speed"), ("wind_gust", "nearby_cwa_wind_gust")]:
        if src in raw.columns:
            values = grouped[src]
            out[f"{prefix}_mean"] = values.mean()
            out[f"{prefix}_max"] = values.max()
            out[f"{prefix}_min"] = values.min()
            out[f"{prefix}_std"] = values.std(ddof=0).fillna(0.0)
            out[f"nearby_cwa_valid_{'wind' if src == 'wind_speed' else 'gust'}_station_count"] = values.count()
    if "precipitation_1hr" in raw.columns:
        precip = grouped["precipitation_1hr"]
        out["nearby_cwa_precipitation_1hr_mean"] = precip.mean()
        out["nearby_cwa_precipitation_1hr_max"] = precip.max()
        out["nearby_cwa_rainy_station_count"] = precip.apply(lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5).sum()))
        out["nearby_cwa_rainy_station_ratio"] = out["nearby_cwa_rainy_station_count"] / out["nearby_cwa_station_count"].replace(0, np.nan)
    if enable_pressure_humidity_features:
        _add_pressure_humidity_aggregates(raw, grouped, out)
    out["nearby_cwa_wind_direction_sin_mean"] = _direction(raw, "wind_direction", np.sin)
    out["nearby_cwa_wind_direction_cos_mean"] = _direction(raw, "wind_direction", np.cos)
    out["nearby_cwa_gust_direction_sin_mean"] = _direction(raw, "wind_gust_direction", np.sin)
    out["nearby_cwa_gust_direction_cos_mean"] = _direction(raw, "wind_gust_direction", np.cos)
    for value_col, out_col in [
        ("wind_speed", "distance_weighted_wind_speed"),
        ("wind_gust", "distance_weighted_wind_gust"),
        ("precipitation_1hr", "distance_weighted_precipitation"),
    ]:
        if value_col in raw.columns:
            out[out_col] = raw.groupby("obs_time").apply(lambda g: _weighted_average(g, value_col), include_groups=False)
    return out.reset_index().rename(columns={"index": "obs_time"})


def _add_pressure_humidity_aggregates(raw: pd.DataFrame, grouped, out: pd.DataFrame) -> None:
    for src, prefix in [
        ("station_pressure", "nearby_cwa_pressure"),
        ("relative_humidity", "nearby_cwa_relative_humidity"),
        ("temperature", "nearby_cwa_temperature"),
    ]:
        if src in raw.columns:
            values = grouped[src]
            out[f"{prefix}_mean"] = values.mean()
            out[f"{prefix}_max"] = values.max()
            out[f"{prefix}_min"] = values.min()
            out[f"{prefix}_std"] = values.std(ddof=0).fillna(0.0)
    if {"nearby_cwa_pressure_max", "nearby_cwa_pressure_min"}.issubset(out.columns):
        out["nearby_cwa_pressure_gradient"] = out["nearby_cwa_pressure_max"] - out["nearby_cwa_pressure_min"]
    if {"nearby_cwa_temperature_mean", "nearby_cwa_relative_humidity_mean"}.issubset(out.columns):
        dew_point = _dew_point_c(out["nearby_cwa_temperature_mean"], out["nearby_cwa_relative_humidity_mean"])
        out["nearby_cwa_dew_point_mean"] = dew_point
        out["nearby_cwa_dew_point_spread_mean"] = out["nearby_cwa_temperature_mean"] - dew_point


def _dew_point_c(temperature_c, relative_humidity_pct):
    """Magnus-Tetens approximation using a=17.625 and b=243.04 degC."""
    temp = pd.to_numeric(temperature_c, errors="coerce")
    rh = pd.to_numeric(relative_humidity_pct, errors="coerce").clip(lower=1e-6, upper=100.0)
    a = 17.625
    b = 243.04
    gamma = np.log(rh / 100.0) + (a * temp) / (b + temp)
    return (b * gamma) / (a - gamma)


def _direction(raw: pd.DataFrame, column: str, fn) -> pd.Series:
    if column not in raw.columns:
        return pd.Series(dtype=float)
    work = raw[["obs_time", column]].copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    work["component"] = fn(np.deg2rad(work[column]))
    return work.groupby("obs_time")["component"].mean()


def _weighted_average(group: pd.DataFrame, column: str) -> float | None:
    values = pd.to_numeric(group[column], errors="coerce")
    distances = pd.to_numeric(group["distance_to_port_km"], errors="coerce")
    weights = 1.0 / (distances.fillna(distances.max()).fillna(0.0) + 1.0)
    valid = values.notna() & weights.notna()
    if not valid.any():
        return None
    return float(np.average(values[valid], weights=weights[valid]))


def _add_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    times = pd.to_datetime(out["obs_time"], errors="coerce")
    hour = times.dt.hour + times.dt.minute / 60.0
    doy = times.dt.dayofyear
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 366.0)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 366.0)
    return out


def _add_lag_roll(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("obs_time").reset_index(drop=True).copy()
    for col in [
        "nearby_cwa_wind_speed_max",
        "nearby_cwa_wind_gust_max",
        "nearby_cwa_precipitation_1hr_max",
        "nearby_cwa_pressure_mean",
        "upstream_subset_wind_speed_max",
        "upstream_subset_wind_gust_max",
        "upstream_subset_precipitation_1hr_max",
    ]:
        if col in out.columns:
            out[f"{col}_lag1"] = out[col].shift(1)
            out[f"{col}_roll3"] = out[col].rolling(3, min_periods=1).mean()
            if col == "nearby_cwa_precipitation_1hr_max":
                out["nearby_cwa_precipitation_roll3"] = out[col].rolling(3, min_periods=1).mean()
                out["nearby_cwa_precipitation_roll6"] = out[col].rolling(6, min_periods=1).mean()
            if col == "upstream_subset_precipitation_1hr_max":
                out["upstream_subset_precipitation_roll3"] = out[col].rolling(3, min_periods=1).mean()
                out["upstream_subset_precipitation_roll6"] = out[col].rolling(6, min_periods=1).mean()
            if col == "nearby_cwa_pressure_mean":
                out["nearby_cwa_pressure_mean_trend_3h"] = out[col] - out[col].shift(3)
    return out


def _add_labels(frame: pd.DataFrame, horizons: dict[str, int]) -> tuple[pd.DataFrame, list[str]]:
    out = frame.sort_values("obs_time").reset_index(drop=True).copy()
    times = pd.DatetimeIndex(pd.to_datetime(out["obs_time"], errors="coerce"))
    source = out.set_index(times)
    labels = []
    for horizon, minutes in horizons.items():
        indexer = times.get_indexer(times + pd.Timedelta(minutes=int(minutes)), method="nearest", tolerance=pd.Timedelta(minutes=30))
        for base, target in [
            ("nearby_cwa_wind_speed_max", f"target_nearby_wind_speed_{horizon}"),
            ("nearby_cwa_wind_gust_max", f"target_nearby_wind_gust_{horizon}"),
        ]:
            out[target] = _values(source, base, indexer)
            labels.append(target)
        rain = f"target_rain_event_{horizon}"
        heavy = f"target_heavy_rain_event_{horizon}"
        vals = _values(source, "nearby_cwa_precipitation_1hr_max", indexer)
        amount = f"target_nearby_precipitation_1hr_{horizon}"
        amount_alias = f"target_nearby_precipitation_amount_{horizon}"
        out[amount] = vals
        out[amount_alias] = vals
        out[rain] = [None if value is None else int(value > 0.5) for value in vals]
        out[heavy] = [None if value is None else int(value > 10.0) for value in vals]
        labels.extend([amount, amount_alias, rain, heavy])
    return out, labels


def _values(source: pd.DataFrame, column: str, indexer) -> list[float | None]:
    if column not in source.columns:
        return [None for _ in indexer]
    values = source[column].to_numpy()
    return [None if pos < 0 or pd.isna(values[pos]) else float(values[pos]) for pos in indexer]


def _horizons(config: dict) -> dict[str, int]:
    anchors = config.get("forecast", {}).get("anchors")
    if isinstance(anchors, dict):
        return {str(key): int(value) for key, value in anchors.items()}
    return {"H1": 30, "H2": 60, "H3": 90, "H4": 120}


def _report(dataset: pd.DataFrame, selected: list[str], features: list[str], labels: list[str]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "sample_count": int(len(dataset)),
        "selected_station_ids": selected,
        "feature_columns": features,
        "label_columns": labels,
    }
