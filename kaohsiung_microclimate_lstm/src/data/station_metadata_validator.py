from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .station_pool import flatten_priority_station_pool
except ImportError:  # pragma: no cover
    from station_pool import flatten_priority_station_pool


def _available_station_ids(available_files: list[str]) -> set[str]:
    ids: set[str] = set()
    for item in available_files:
        path = Path(str(item))
        ids.add(path.stem if path.suffix else str(item))
    return ids


def validate_station_metadata(station_pool_config: dict[str, Any], available_files: list[str]) -> dict[str, Any]:
    available_ids = _available_station_ids(available_files)
    stations = flatten_priority_station_pool(station_pool_config, include_reference=True)
    known_ids = {str(station["station_id"]) for station in stations}
    invalid: list[str] = []
    valid_port_local: list[str] = []
    missing_port_local: list[str] = []
    fallback_stations: list[str] = []
    unknown_station_ids = sorted(available_ids - known_ids)

    for station in stations:
        station_id = str(station["station_id"])
        group = str(station.get("priority_group", ""))
        is_port_local = bool(station.get("is_port_local", False))
        is_core = bool(station.get("is_core_station", False))

        if station_id.startswith(("KHWD", "KHTD", "KHAW")) and not is_port_local:
            invalid.append(f"{station_id}: port-local station must set is_port_local=true")
        if station_id == "467441":
            if is_port_local:
                invalid.append("467441: fallback station must set is_port_local=false")
            if is_core or group == "port_local_wind" or station.get("priority") == 1:
                invalid.append("467441: fallback station cannot be a priority-1 core station")
            if station.get("role") != "fallback_baseline" and station.get("usage") != "fallback_only":
                invalid.append("467441: role must be fallback_baseline/fallback_only")

        if is_port_local:
            if station_id in available_ids:
                valid_port_local.append(station_id)
            else:
                missing_port_local.append(station_id)
        if station.get("role") == "fallback_baseline" or station.get("usage") == "fallback_only":
            fallback_stations.append(station_id)

    return {
        "is_valid": len(invalid) == 0,
        "invalid_reasons": invalid,
        "valid_port_local_stations": valid_port_local,
        "missing_port_local_stations": missing_port_local,
        "fallback_stations": fallback_stations,
        "unknown_station_ids": unknown_station_ids,
        "station_metadata_report": {
            "station_pool_version": station_pool_config.get("station_pool_version"),
            "known_station_count": len(known_ids),
            "available_file_count": len(available_ids),
            "467441_used_as_core_station": any(
                str(station.get("station_id")) == "467441"
                and (bool(station.get("is_core_station", False)) or station.get("priority") == 1)
                for station in stations
            ),
            "station_priority_policy": "port_local_first",
        },
    }
