from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any


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
