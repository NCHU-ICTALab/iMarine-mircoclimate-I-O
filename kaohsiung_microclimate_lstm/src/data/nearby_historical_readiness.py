from __future__ import annotations

from typing import Any

import pandas as pd


def check_nearby_historical_training_readiness(
    station_frames: dict[str, pd.DataFrame],
    selected_station_ids: list[str],
    config: dict,
) -> dict[str, Any]:
    cfg = config.get("nearby_cwa_historical_training", {})
    thresholds = cfg.get("training_thresholds", {})
    min_stations = int(cfg.get("min_selected_stations", 2))
    min_total = int(thresholds.get("min_total_samples", cfg.get("min_total_samples", 1000)))
    min_days = int(thresholds.get("min_training_days", cfg.get("min_training_days", 30)))
    min_wind = int(thresholds.get("min_valid_wind_samples", 500))
    min_gust = int(thresholds.get("min_valid_gust_samples", 500))
    min_rain = int(thresholds.get("min_valid_rain_samples", 500))
    selected = [sid for sid in selected_station_ids if sid in station_frames and station_frames[sid] is not None and not station_frames[sid].empty]
    frames = [station_frames[sid].copy() for sid in selected]
    failed: list[str] = []
    warnings: list[str] = []
    if len(selected) < min_stations:
        failed.append("selected station count below threshold")
    if not frames:
        return {
            "ready": False,
            "selected_station_ids": selected,
            "station_count": 0,
            "sample_count": 0,
            "training_days": 0,
            "valid_wind_samples": 0,
            "valid_gust_samples": 0,
            "valid_rain_samples": 0,
            "failed_reasons": failed or ["no nearby historical station data available"],
            "warnings": warnings,
        }
    merged = pd.concat(frames, ignore_index=True)
    merged["obs_time"] = pd.to_datetime(merged["obs_time"], errors="coerce")
    merged = merged.dropna(subset=["obs_time"])
    sample_count = int(len(merged))
    training_days = 0
    if not merged.empty:
        training_days = int(max(0, (merged["obs_time"].max() - merged["obs_time"].min()).total_seconds() // 86400))
    valid_wind = _valid_count(merged, "wind_speed")
    valid_gust = _valid_count(merged, "wind_gust")
    valid_rain = _valid_count(merged, "precipitation_1hr")
    if sample_count < min_total:
        failed.append("sample_count below min_total_samples")
    if training_days < min_days:
        failed.append("training_days below min_training_days")
    if valid_wind < min_wind:
        failed.append("valid_wind_samples below threshold")
    if valid_gust < min_gust:
        failed.append("valid_gust_samples below threshold")
    if valid_rain < min_rain:
        failed.append("valid_rain_samples below threshold")
    return {
        "ready": not failed,
        "selected_station_ids": selected,
        "station_count": len(selected),
        "sample_count": sample_count,
        "training_days": training_days,
        "valid_wind_samples": valid_wind,
        "valid_gust_samples": valid_gust,
        "valid_rain_samples": valid_rain,
        "failed_reasons": failed,
        "warnings": warnings,
    }


def _valid_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").notna().sum())
