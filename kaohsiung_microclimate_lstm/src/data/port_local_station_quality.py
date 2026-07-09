from __future__ import annotations

from typing import Any

import pandas as pd


def validate_port_local_station_frame(df: pd.DataFrame, station_id: str, station_type: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "station_id": str(station_id),
            "station_type": str(station_type),
            "valid": False,
            "record_count": 0,
            "time_start": None,
            "time_end": None,
            "missing_ratio": {},
            "out_of_range_count": {},
            "quality_status": "unavailable",
            "warnings": ["record_count=0"],
        }

    work = df.copy()
    time_col = "obs_time" if "obs_time" in work.columns else "timestamp" if "timestamp" in work.columns else None
    times = pd.to_datetime(work[time_col], errors="coerce") if time_col else pd.Series(dtype="datetime64[ns]")
    checks = _range_checks(str(station_type))
    missing_ratio = {}
    out_of_range_count = {}
    warnings: list[str] = []

    for column, (low, high) in checks.items():
        values = pd.to_numeric(work[column], errors="coerce") if column in work.columns else pd.Series([None] * len(work))
        missing_ratio[column] = round(float(values.isna().mean()), 4) if len(values) else 1.0
        out_of_range_count[column] = int(((values < low) | (values > high)).sum()) if len(values) else 0
        if missing_ratio[column] > 0.5:
            warnings.append(f"{column}: missing_ratio > 0.5")
        if out_of_range_count[column] > 0:
            warnings.append(f"{column}: out_of_range")

    if str(station_type) == "wind" and {"wind_speed", "wind_gust"}.issubset(work.columns):
        speed = pd.to_numeric(work["wind_speed"], errors="coerce")
        gust = pd.to_numeric(work["wind_gust"], errors="coerce")
        if int((gust < speed).sum()) > 0:
            warnings.append("wind_gust lower than wind_speed")

    quality_status = "ok"
    if any(value > 0 for value in out_of_range_count.values()) or any(value > 0.5 for value in missing_ratio.values()):
        quality_status = "degraded"
    valid = quality_status == "ok" or (len(work) > 0 and not all(value > 0.5 for value in missing_ratio.values()))
    return {
        "station_id": str(station_id),
        "station_type": str(station_type),
        "valid": bool(valid),
        "record_count": int(len(work)),
        "time_start": None if times.empty or times.isna().all() else times.min().isoformat(),
        "time_end": None if times.empty or times.isna().all() else times.max().isoformat(),
        "missing_ratio": missing_ratio,
        "out_of_range_count": out_of_range_count,
        "quality_status": quality_status,
        "warnings": warnings,
    }


def _range_checks(station_type: str) -> dict[str, tuple[float, float]]:
    if station_type == "wind":
        return {"wind_speed": (0.0, 60.0), "wind_gust": (0.0, 100.0), "wind_direction": (0.0, 360.0)}
    if station_type == "tide":
        return {"tide_level_cm": (-500.0, 800.0)}
    return {"wave_height_m": (0.0, 20.0), "wave_period_s": (0.0, 30.0), "current_speed": (0.0, 10.0), "current_direction": (0.0, 360.0)}
