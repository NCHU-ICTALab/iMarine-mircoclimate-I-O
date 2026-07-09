from __future__ import annotations

from typing import Any

import pandas as pd


def build_port_local_wind_features(khwd_frames: dict[str, pd.DataFrame], config: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for station_id, frame in khwd_frames.items():
        if frame is None or frame.empty:
            warnings.append(f"{station_id}: empty")
            continue
        work = frame.copy()
        if "obs_time" in work.columns:
            work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
            work = work.sort_values("obs_time")
        row = work.iloc[-1].to_dict()
        row["station_id"] = str(station_id)
        rows.append(row)

    if not rows:
        return {
            "features": {
                "khwd_station_count": 0,
                "khwd_valid_wind_station_count": 0,
                "khwd_valid_gust_station_count": 0,
            },
            "station_ids_used": [],
            "station_count": 0,
            "data_time_latest": None,
            "quality_status": "unavailable",
            "warnings": warnings or ["No KHWD station data available."],
        }

    latest = pd.DataFrame(rows)
    wind = pd.to_numeric(latest.get("wind_speed", pd.Series(dtype=float)), errors="coerce")
    gust = pd.to_numeric(latest.get("wind_gust", pd.Series(dtype=float)), errors="coerce")
    times = pd.to_datetime(latest.get("obs_time", latest.get("timestamp", pd.Series(dtype=str))), errors="coerce")
    features = {
        "khwd_wind_speed_mean": _round_or_none(wind.mean()),
        "khwd_wind_speed_max": _round_or_none(wind.max()),
        "khwd_wind_speed_min": _round_or_none(wind.min()),
        "khwd_wind_speed_std": _round_or_none(wind.std(ddof=0)),
        "khwd_wind_gust_mean": _round_or_none(gust.mean()),
        "khwd_wind_gust_max": _round_or_none(gust.max()),
        "khwd_wind_gust_min": _round_or_none(gust.min()),
        "khwd_wind_gust_std": _round_or_none(gust.std(ddof=0)),
        "khwd_station_count": int(len(latest)),
        "khwd_valid_wind_station_count": int(wind.notna().sum()),
        "khwd_valid_gust_station_count": int(gust.notna().sum()),
        "khwd_latest_observation_time": None if times.empty or times.isna().all() else times.max().isoformat(),
    }
    quality = "ok"
    if features["khwd_valid_wind_station_count"] < int(config.get("port_local_wind_postprocess", {}).get("min_required_khwd_stations", 2)):
        quality = "degraded"
        warnings.append("Valid KHWD wind station count below minimum.")
    return {
        "features": features,
        "station_ids_used": [str(item) for item in latest["station_id"].tolist()],
        "station_count": int(len(latest)),
        "data_time_latest": features["khwd_latest_observation_time"],
        "quality_status": quality,
        "warnings": warnings,
    }


def _round_or_none(value: Any) -> float | None:
    return None if pd.isna(value) else round(float(value), 4)
