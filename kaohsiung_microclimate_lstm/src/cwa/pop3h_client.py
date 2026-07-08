from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from urllib3.exceptions import InsecureRequestWarning

try:
    from ..data.check_qpesums_availability import BASE_URL, load_api_key
except ImportError:  # pragma: no cover
    from data.check_qpesums_availability import BASE_URL, load_api_key


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

DATAID = "F-D0047-065"
TZ_TPE = ZoneInfo("Asia/Taipei")


def fetch_pop3h(
    location_name: str,
    api_key: str | None = None,
    now: datetime | None = None,
    cache_minutes: int = 30,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
) -> dict[str, Any]:
    now = now or datetime.now(tz=TZ_TPE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_TPE)
    cache_path = Path(project_root) / "data" / "cache" / f"cwa_pop3h_{_safe_name(location_name)}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - float(cached.get("_cached_at", 0)) < cache_minutes * 60:
            return _current_next(cached["payload"], now)
    key = api_key or load_api_key()
    if not key:
        return _unavailable(location_name, "missing CWA_API_KEY")
    try:
        resp = requests.get(
            f"{BASE_URL}/{DATAID}",
            params={"Authorization": key, "format": "JSON", "locationName": location_name, "elementName": "PoP3h"},
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        records = _parse_records(resp.json(), location_name)
        payload = {
            "available": bool(records),
            "location_name": location_name,
            "records": records,
            "fetched_at": datetime.now(tz=TZ_TPE).isoformat(timespec="seconds"),
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"_cached_at": time.time(), "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        return _current_next(payload, now)
    except Exception as exc:
        return _unavailable(location_name, str(exc))


def _parse_records(body: dict[str, Any], location_name: str) -> list[dict[str, Any]]:
    groups = body.get("records", {}).get("Locations", [])
    locations = groups[0].get("Location", []) if groups else body.get("records", {}).get("Location", [])
    loc = next((item for item in locations if item.get("LocationName") == location_name), None)
    if not loc and locations:
        loc = locations[0]
    if not loc:
        return []
    elem = next((item for item in loc.get("WeatherElement", []) if item.get("ElementName") == "PoP3h"), None)
    if not elem:
        return []
    rows = []
    for item in elem.get("Time", []):
        value = item.get("ElementValue", [{}])[0]
        raw_pop = value.get("ProbabilityOfPrecipitation") or value.get("PoP3h") or value.get("Value") or 0
        pop = float(raw_pop)
        if pop > 1.0:
            pop /= 100.0
        rows.append(
            {
                "start_time": datetime.fromisoformat(item["StartTime"]).astimezone(TZ_TPE).isoformat(),
                "end_time": datetime.fromisoformat(item["EndTime"]).astimezone(TZ_TPE).isoformat(),
                "pop": min(max(pop, 0.0), 1.0),
            }
        )
    return rows


def _current_next(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    records = payload.get("records", [])
    current = None
    next_value = None
    for idx, record in enumerate(records):
        start = datetime.fromisoformat(record["start_time"]).astimezone(TZ_TPE)
        end = datetime.fromisoformat(record["end_time"]).astimezone(TZ_TPE)
        if start <= now < end:
            current = float(record["pop"])
            next_value = float(records[idx + 1]["pop"]) if idx + 1 < len(records) else current
            break
    if current is None and records:
        current = float(records[0]["pop"])
        next_value = float(records[1]["pop"]) if len(records) > 1 else current
    return {
        "available": bool(payload.get("available", False) and current is not None),
        "location_name": payload.get("location_name"),
        "current": current,
        "next": next_value,
        "records": records,
        "fetched_at": payload.get("fetched_at"),
    }


def _unavailable(location_name: str, reason: str) -> dict[str, Any]:
    return {"available": False, "location_name": location_name, "current": None, "next": None, "records": [], "fetched_at": None, "reason": reason}


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)
