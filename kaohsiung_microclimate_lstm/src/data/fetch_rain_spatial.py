from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

try:
    from .check_qpesums_availability import BASE_URL, load_api_key
except ImportError:  # pragma: no cover
    from check_qpesums_availability import BASE_URL, load_api_key


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

DATAID = "O-A0002-001"
PORT_LAT = 22.62
PORT_LON = 120.28
RADIUS_KM = 30.0
TOP_N = 3


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(a))


def build_station_list(
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    force_refresh: bool = False,
    radius_km: float = RADIUS_KM,
    top_n: int = TOP_N,
) -> list[dict[str, Any]]:
    cache_path = Path(project_root) / "data" / "cache" / "nearby_rain_stations.json"
    if cache_path.exists() and not force_refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("CWA_API_KEY is not available")
    resp = requests.get(
        f"{BASE_URL}/{DATAID}",
        params={"Authorization": api_key, "format": "JSON"},
        timeout=20,
        verify=False,
    )
    resp.raise_for_status()
    stations = resp.json().get("records", {}).get("Station", [])
    nearby = []
    for station in stations:
        lat, lon = _station_lat_lon(station)
        if lat is None or lon is None:
            continue
        dist = haversine_km(PORT_LAT, PORT_LON, lat, lon)
        if dist <= radius_km:
            nearby.append(
                {
                    "station_id": station.get("StationId") or station.get("StationID"),
                    "name": station.get("StationName"),
                    "lat": lat,
                    "lon": lon,
                    "dist_km": round(dist, 2),
                }
            )
    nearby.sort(key=lambda item: item["dist_km"])
    result = nearby[:top_n]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def fetch_nearby_precip_now(project_root: str | Path = "kaohsiung_microclimate_lstm") -> dict[str, Any]:
    stations = build_station_list(project_root)
    if not stations:
        return {"obs_time": None, "nearby": [], "available": False}
    api_key = load_api_key()
    if not api_key:
        return {"obs_time": None, "nearby": [], "available": False}
    try:
        resp = requests.get(
            f"{BASE_URL}/{DATAID}",
            params={
                "Authorization": api_key,
                "format": "JSON",
                "StationId": ",".join(str(station["station_id"]) for station in stations),
            },
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        records = {row.get("StationId") or row.get("StationID"): row for row in resp.json().get("records", {}).get("Station", [])}
    except Exception:
        return {"obs_time": None, "nearby": [], "available": False}

    result = []
    obs_time = None
    for station in stations:
        rec = records.get(station["station_id"], {})
        obs = rec.get("ObsTime")
        if isinstance(obs, dict):
            obs_time = obs.get("DateTime") or obs_time
        elif obs:
            obs_time = obs
        result.append({**station, "precip_1hr": _rainfall_1hr(rec)})
    return {"obs_time": obs_time, "nearby": result, "available": True}


def to_feature_vector(nearby_result: dict[str, Any], top_n: int = TOP_N) -> dict[str, float]:
    available = float(bool(nearby_result.get("available", False)))
    nearby = nearby_result.get("nearby", []) if available else []
    feats = {"nearby_available": available}
    for idx in range(1, top_n + 1):
        feats[f"nearby_precip_{idx}"] = float(nearby[idx - 1].get("precip_1hr", 0.0)) if len(nearby) >= idx else 0.0
    return feats


def _station_lat_lon(station: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = station.get("GeoInfo", {}).get("Coordinates", [])
    coord = coords[0] if coords and isinstance(coords[0], dict) else {}
    lat = station.get("StationLatitude") or coord.get("StationLatitude")
    lon = station.get("StationLongitude") or coord.get("StationLongitude")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _rainfall_1hr(station: dict[str, Any]) -> float:
    rainfall = station.get("RainfallElement", {})
    for group in ("Past1hr", "Now"):
        value = rainfall.get(group, {}).get("Precipitation")
        if value is not None:
            try:
                return float(value or 0.0)
            except ValueError:
                return 0.0
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    parser.add_argument("--force_refresh", action="store_true")
    args = parser.parse_args()
    stations = build_station_list(args.project_root, force_refresh=args.force_refresh)
    print(json.dumps({"stations": stations, "latest": fetch_nearby_precip_now(args.project_root)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
