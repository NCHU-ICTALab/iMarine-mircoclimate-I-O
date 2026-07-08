from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from urllib3.exceptions import InsecureRequestWarning

try:
    from .check_qpesums_availability import BASE_URL, load_api_key
except ImportError:  # pragma: no cover
    from check_qpesums_availability import BASE_URL, load_api_key


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

DATAID = "F-D0047-065"
TARGET_LOCATION = "鼓山區"
TZ_TPE = ZoneInfo("Asia/Taipei")
CACHE_TTL = 3600


def fetch_pop3h(
    location: str = TARGET_LOCATION,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    cache_ttl: int = CACHE_TTL,
) -> list[dict[str, Any]]:
    cache_path = Path(project_root) / "data" / "cache" / "cwa_pop3h_latest.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - float(cached.get("_cached_at", 0)) < cache_ttl:
            return list(cached.get("data", []))
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("CWA_API_KEY is not available")
    resp = requests.get(
        f"{BASE_URL}/{DATAID}",
        params={"Authorization": api_key, "format": "JSON", "locationName": location, "elementName": "PoP3h"},
        timeout=20,
        verify=False,
    )
    resp.raise_for_status()
    body = resp.json()
    locations_group = body.get("records", {}).get("Locations", [])
    locations = locations_group[0].get("Location", []) if locations_group else body.get("records", {}).get("Location", [])
    loc_data = next((item for item in locations if item.get("LocationName") == location), None)
    if not loc_data and locations:
        loc_data = locations[0]
    if not loc_data:
        raise ValueError(f"No forecast location found for {location}")
    elements = loc_data.get("WeatherElement", [])
    pop_elem = next((item for item in elements if item.get("ElementName") == "PoP3h"), None)
    if not pop_elem:
        raise ValueError("PoP3h element not found")
    result = []
    for item in pop_elem.get("Time", []):
        value = item.get("ElementValue", [{}])[0]
        pop_pct = value.get("ProbabilityOfPrecipitation") or value.get("PoP3h") or value.get("Value") or 0
        result.append(
            {
                "start": datetime.fromisoformat(item["StartTime"]).astimezone(TZ_TPE).isoformat(),
                "end": datetime.fromisoformat(item["EndTime"]).astimezone(TZ_TPE).isoformat(),
                "pop3h": float(pop_pct) / 100.0,
            }
        )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"_cached_at": time.time(), "data": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def get_pop_features(
    reference_time: datetime | None = None,
    location: str = TARGET_LOCATION,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    cache_ttl: int = CACHE_TTL,
) -> dict[str, float]:
    reference_time = reference_time or datetime.now(tz=TZ_TPE)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=TZ_TPE)
    try:
        forecast = fetch_pop3h(location=location, project_root=project_root, cache_ttl=cache_ttl)
    except Exception:
        return {"cwa_pop_current": 0.0, "cwa_pop_next": 0.0, "cwa_data_age_hr": 1.0, "cwa_available": 0.0}

    current_pop = 0.0
    next_pop = 0.0
    for idx, slot in enumerate(forecast):
        start = datetime.fromisoformat(slot["start"]).astimezone(TZ_TPE)
        end = datetime.fromisoformat(slot["end"]).astimezone(TZ_TPE)
        if start <= reference_time < end:
            current_pop = float(slot["pop3h"])
            next_pop = float(forecast[idx + 1]["pop3h"]) if idx + 1 < len(forecast) else current_pop
            break

    release_hours = [5.5, 11.5, 17.5, 23.5]
    now_hour = reference_time.hour + reference_time.minute / 60
    past = [hour for hour in release_hours if hour <= now_hour]
    last_release = max(past) if past else release_hours[-1] - 24
    data_age_hr = min(1.0, max(0.0, (now_hour - last_release) / 6.0))
    return {
        "cwa_pop_current": current_pop,
        "cwa_pop_next": next_pop,
        "cwa_data_age_hr": round(data_age_hr, 4),
        "cwa_available": 1.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    parser.add_argument("--location", default=TARGET_LOCATION)
    args = parser.parse_args()
    print(json.dumps(get_pop_features(location=args.location, project_root=args.project_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
