from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any


TAIPEI = timezone(timedelta(hours=8))


def rank_nearby_cwa_stations(
    station_metadata: list[dict],
    port_reference_points: list[dict],
    baseline_station_id: str = "467441",
    config: dict | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    max_selected = int(cfg.get("nearby_cwa_historical_training", {}).get("max_selected_stations", 6))
    priority_1 = set(cfg.get("nearby_cwa_historical_training", {}).get("priority_1_station_ids", []))
    baseline = next((item for item in station_metadata if str(item.get("station_id")) == str(baseline_station_id)), None)
    if not baseline:
        raise ValueError(f"baseline station not found: {baseline_station_id}")
    baseline_distance = _min_distance_to_port(baseline, port_reference_points)
    ranked: list[dict[str, Any]] = []
    for station in station_metadata:
        station_id = str(station.get("station_id"))
        distance = _min_distance_to_port(station, port_reference_points)
        closer = distance < baseline_distance and station_id != str(baseline_station_id)
        ranked.append(
            {
                **station,
                "distance_to_port_km": round(distance, 4),
                "closer_than_467441": closer,
                "priority_group": "priority_1_near_port" if station_id in priority_1 else station.get("priority_group", "priority_2_outer_nearby"),
                "selected": False,
            }
        )
    ranked.sort(key=lambda item: (0 if str(item["station_id"]) in priority_1 else 1, item["distance_to_port_km"]))
    selected = [item for item in ranked if item["closer_than_467441"] and str(item["station_id"]) != str(baseline_station_id)]
    selected = selected[:max_selected]
    selected_ids = [str(item["station_id"]) for item in selected]
    for item in ranked:
        item["selected"] = str(item["station_id"]) in selected_ids
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "baseline_station": {
            "station_id": str(baseline_station_id),
            "name": baseline.get("name"),
            "distance_to_port_km": round(baseline_distance, 4),
        },
        "ranked_candidates": ranked,
        "selected_station_ids": selected_ids,
        "all_selected_stations_closer_than_467441": all(item["closer_than_467441"] for item in selected),
    }
    return {
        "ranked_stations": ranked,
        "stations_closer_than_baseline": [item for item in ranked if item["closer_than_467441"]],
        "baseline_distance_km": round(baseline_distance, 4),
        "selected_station_ids": selected_ids,
        "ranking_report": report,
    }


def _min_distance_to_port(station: dict, points: list[dict]) -> float:
    lon = float(station["longitude"])
    lat = float(station["latitude"])
    return min(_haversine_km(lat, lon, float(point["latitude"]), float(point["longitude"])) for point in points)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))
