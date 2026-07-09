from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import yaml


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0
    d_lat = radians(b_lat - a_lat)
    d_lon = radians(b_lon - a_lon)
    aa = sin(d_lat / 2) ** 2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(d_lon / 2) ** 2
    return 2 * radius * asin(sqrt(aa))


def build_station_pool(target_station_id: str, station_metadata: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    scope = config.get("spatial_scope", {})
    pool_cfg = scope.get("station_pool", {})
    max_radius = float(pool_cfg.get("max_radius_km", 10))
    target = next((item for item in station_metadata if str(item.get("station_id")) == str(target_station_id)), None)
    selected: list[dict[str, Any]] = []
    excluded = 0
    for station in station_metadata:
        station_id = str(station.get("station_id"))
        if station_id == str(target_station_id):
            continue
        include = True
        distance = None
        if target and all(k in target and k in station for k in ("lat", "lon")):
            distance = _distance_km(float(target["lat"]), float(target["lon"]), float(station["lat"]), float(station["lon"]))
            include = distance <= max_radius
        if include:
            item = dict(station)
            if distance is not None:
                item["distance_km"] = round(distance, 3)
            selected.append(item)
        else:
            excluded += 1
    return {
        "target_station_id": str(target_station_id),
        "station_pool": selected,
        "included_station_count": len(selected),
        "excluded_station_count": excluded,
        "selection_mode": str(pool_cfg.get("mode", "distance_or_manual")),
    }


def load_station_pool_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def enabled_input_stations(station_pool_config: dict[str, Any]) -> list[dict[str, Any]]:
    if "priority_groups" in station_pool_config:
        return flatten_priority_station_pool(station_pool_config, include_reference=True)
    rules = station_pool_config.get("selection_rules", {})
    include_enabled_only = bool(rules.get("include_enabled_only", True))
    stations = []
    for station in station_pool_config.get("input_stations", []):
        if include_enabled_only and not bool(station.get("enabled", True)):
            continue
        if not station.get("station_id"):
            continue
        stations.append({**station, "station_id": str(station["station_id"])})
    return stations


def flatten_priority_station_pool(station_pool_config: dict[str, Any], include_reference: bool = True) -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = []
    groups = station_pool_config.get("priority_groups", {})
    for group_name, group in sorted(groups.items(), key=lambda item: int(item[1].get("priority", 999))):
        if group_name == "cwa_forecast_auxiliary":
            continue
        if not include_reference and group.get("role") == "reference_only":
            continue
        for station in group.get("stations", []) or []:
            if not bool(station.get("enabled", True)) or not station.get("station_id"):
                continue
            stations.append(
                {
                    **station,
                    "station_id": str(station["station_id"]),
                    "priority_group": group_name,
                    "priority": int(group.get("priority", 999)),
                    "required_for_core_prediction": bool(group.get("required_for_core_prediction", False)),
                    "group_role": group.get("role"),
                }
            )
    return stations


def resolve_station_pool_path(config: dict[str, Any], project_root: str | Path) -> Path:
    pool_path = Path(config.get("station_pool", {}).get("station_pool_config", "config/station_pool.yaml"))
    if not pool_path.is_absolute():
        pool_path = Path(project_root) / pool_path
    return pool_path
