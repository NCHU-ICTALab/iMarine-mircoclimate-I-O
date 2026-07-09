from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

try:
    from ..preprocess import load_observations
    from .station_metadata_validator import validate_station_metadata
    from .station_pool import flatten_priority_station_pool
    from .station_priority import decide_prediction_mode
except ImportError:  # pragma: no cover
    from preprocess import load_observations
    from data.station_metadata_validator import validate_station_metadata
    from data.station_pool import flatten_priority_station_pool
    from data.station_priority import decide_prediction_mode


def load_multi_station_observations(
    station_pool: list[dict[str, Any]],
    data_dir: str | Path,
    target_station_id: str,
    required_columns: list[str] | None = None,
) -> dict[str, Any]:
    data_root = Path(data_dir)
    station_frames: dict[str, pd.DataFrame] = {}
    missing_station_ids: list[str] = []
    required = set(required_columns or [])
    target = str(target_station_id)

    for station in station_pool:
        station_id = str(station.get("station_id", ""))
        if not station_id:
            continue
        path = data_root / f"{station_id}.csv"
        if not path.exists():
            missing_station_ids.append(station_id)
            continue
        frame = load_observations(path)
        if required and not required.issubset(set(frame.columns)):
            missing_station_ids.append(station_id)
            continue
        if frame.empty:
            missing_station_ids.append(station_id)
            continue
        station_frames[station_id] = frame

    if target not in station_frames:
        raise FileNotFoundError(f"Target station observation file not found: {target}")

    available_station_ids = list(station_frames)
    nearby_available = [station_id for station_id in available_station_ids if station_id != target]
    fallback_to_single_station = len(nearby_available) == 0
    return {
        "target_station_id": target,
        "available_station_ids": available_station_ids,
        "missing_station_ids": missing_station_ids,
        "station_frames": station_frames,
        "input_station_count": len(available_station_ids),
        "multi_station_input": not fallback_to_single_station,
        "fallback_to_single_station": fallback_to_single_station,
        "fallback_reason": "Only target station data available." if fallback_to_single_station else None,
    }


def load_priority_station_pool_observations(
    station_pool_config: dict[str, Any],
    data_dir: str | Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    data_root = Path(data_dir)
    files = [path.name for path in data_root.glob("*.csv")] if data_root.exists() else []
    validation = validate_station_metadata(station_pool_config, files)
    station_frames: dict[str, pd.DataFrame] = {}
    missing_station_ids: list[str] = []

    for station in flatten_priority_station_pool(station_pool_config, include_reference=True):
        station_id = str(station.get("station_id"))
        path = data_root / f"{station_id}.csv"
        if not path.exists():
            missing_station_ids.append(station_id)
            continue
        try:
            frame = load_observations(path)
        except Exception:
            missing_station_ids.append(station_id)
            continue
        if frame.empty:
            missing_station_ids.append(station_id)
            continue
        station_frames[station_id] = frame

    port_local_ids = [
        str(station["station_id"])
        for station in flatten_priority_station_pool(station_pool_config, include_reference=True)
        if bool(station.get("is_port_local", False))
    ]
    port_local_wind_ids = [
        str(station["station_id"])
        for station in flatten_priority_station_pool(station_pool_config, include_reference=True)
        if station.get("priority_group") == "port_local_wind"
    ]
    available_port_local_ids = [station_id for station_id in port_local_ids if station_id in station_frames]
    available_port_local_wind_ids = [station_id for station_id in port_local_wind_ids if station_id in station_frames]
    fallback_station_ids = [station_id for station_id in ["467441"] if station_id in station_frames]
    station_availability = {
        "available_port_local_station_ids": available_port_local_ids,
        "available_port_local_wind_station_ids": available_port_local_wind_ids,
        "missing_port_local_station_ids": [station_id for station_id in port_local_ids if station_id not in station_frames],
        "fallback_station_ids": fallback_station_ids,
    }
    mode = decide_prediction_mode(station_availability, None, config)
    fallback_used = bool(mode["fallback_to_467441"])
    return {
        "prediction_mode": mode["prediction_mode"],
        "port_local_station_ids": port_local_ids,
        "available_port_local_station_ids": available_port_local_ids,
        "available_port_local_wind_station_ids": available_port_local_wind_ids,
        "missing_port_local_station_ids": station_availability["missing_port_local_station_ids"],
        "fallback_station_ids": fallback_station_ids,
        "fallback_used": fallback_used,
        "fallback_reason": mode.get("fallback_reason"),
        "station_frames": station_frames,
        "station_priority_report": {
            "station_pool_version": station_pool_config.get("station_pool_version"),
            "station_pool_mode": station_pool_config.get("station_pool_mode"),
            "station_priority_policy": "port_local_first",
            "metadata_validation": validation,
            "mode_decision": mode,
            "available_station_ids": list(station_frames),
            "missing_station_ids": missing_station_ids,
        },
    }
