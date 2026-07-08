from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

try:
    from .check_qpesums_availability import BASE_URL, load_api_key
    from .qpesums_cache import get_cached
except ImportError:  # pragma: no cover
    from check_qpesums_availability import BASE_URL, load_api_key
    from qpesums_cache import get_cached


PORT_LAT = 22.62
PORT_LON = 120.28
SEARCH_RADIUS = 0.1
DATAID_QPE = "O-A0002-001"
DATAID_QPF: str | None = None


def fetch_qpe_current(
    api_key: str | None = None,
    dataid: str = DATAID_QPE,
    lat: float = PORT_LAT,
    lon: float = PORT_LON,
    radius: float = SEARCH_RADIUS,
) -> dict[str, Any]:
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("CWA_API_KEY is not available")
    resp = requests.get(f"{BASE_URL}/{dataid}", params={"Authorization": key, "format": "JSON"}, timeout=20, verify=False)
    resp.raise_for_status()
    records = resp.json().get("records", {})
    nearest = _find_nearest(records, lat, lon, radius)
    if not nearest:
        raise RuntimeError("No QPESUMS/QPE station found near target location")
    return {
        "obs_time": nearest.get("ObsTime") or nearest.get("WeatherElement", {}).get("ObsTime"),
        "qpe_1hr_mm": _precip_value(nearest, "1hr"),
        "qpe_3hr_mm": _precip_value(nearest, "3hr"),
        "station_id": nearest.get("StationId") or nearest.get("StationID"),
        "station_name": nearest.get("StationName"),
        "data_source": dataid,
    }


def fetch_qpf_anchors(api_key: str | None = None, dataid: str | None = DATAID_QPF) -> dict[str, float] | None:
    if not dataid:
        return None
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("CWA_API_KEY is not available")
    resp = requests.get(f"{BASE_URL}/{dataid}", params={"Authorization": key, "format": "JSON"}, timeout=20, verify=False)
    resp.raise_for_status()
    records = resp.json().get("records", {})
    nearest = _find_nearest(records, PORT_LAT, PORT_LON, SEARCH_RADIUS)
    forecasts = nearest.get("Forecasts", []) if nearest else []
    result: dict[str, float] = {}
    for fc in forecasts:
        offset = int(fc.get("OffsetMinutes", 0) or 0)
        if offset in {30, 60, 90, 120}:
            result[f"qpf_{offset}min_mm"] = float(fc.get("Precipitation", 0) or 0)
    return result or None


def get_qpe_current_cached(project_root: str | Path = "kaohsiung_microclimate_lstm", ttl_seconds: int = 600) -> dict[str, Any]:
    return get_cached(Path(project_root) / "data" / "cache" / "qpesums_latest.json", ttl_seconds, fetch_qpe_current)


def build_qpe_timeseries(lookback_hours: int = 12, project_root: str | Path = "kaohsiung_microclimate_lstm") -> pd.DataFrame:
    current = get_qpe_current_cached(project_root)
    now = datetime.now()
    records = []
    for h in range(lookback_hours, 0, -1):
        records.append(
            {
                "obs_time": now - timedelta(hours=h),
                "qpe_1hr_mm": float(current.get("qpe_1hr_mm", 0.0) or 0.0),
                "qpe_3hr_mm": float(current.get("qpe_3hr_mm", 0.0) or 0.0),
            }
        )
    return pd.DataFrame(records)


def _find_nearest(records: dict[str, Any], lat: float, lon: float, radius: float) -> dict[str, Any]:
    stations = records.get("Station", []) if isinstance(records, dict) else []
    best: dict[str, Any] = {}
    best_dist = float("inf")
    for station in stations:
        coords = station.get("GeoInfo", {}).get("Coordinates", [])
        coord = coords[0] if coords and isinstance(coords[0], dict) else {}
        s_lat = float(station.get("StationLatitude", 0) or coord.get("StationLatitude", 0) or 0)
        s_lon = float(station.get("StationLongitude", 0) or coord.get("StationLongitude", 0) or 0)
        dist = ((s_lat - lat) ** 2 + (s_lon - lon) ** 2) ** 0.5
        if dist < best_dist and dist <= radius:
            best = station
            best_dist = dist
    return best


def _precip_value(station: dict[str, Any], key: str) -> float:
    precip = station.get("Precipitation", {}).get("Accumulation", {})
    if key in precip:
        return float(precip.get(key) or 0.0)
    weather = station.get("WeatherElement", {})
    rain = weather.get("Now", {}).get("Precipitation") or weather.get("Past1hr", {}).get("Precipitation")
    if key == "1hr" and rain is not None:
        return float(rain or 0.0)
    rainfall = station.get("RainfallElement", {})
    if key == "1hr":
        return float(rainfall.get("Past1hr", {}).get("Precipitation", 0) or rainfall.get("Now", {}).get("Precipitation", 0) or 0)
    if key == "3hr":
        return float(rainfall.get("Past3hr", {}).get("Precipitation", 0) or 0)
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    args = parser.parse_args()
    print(json.dumps(get_qpe_current_cached(args.project_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
