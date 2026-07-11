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
EXTENDED_DATAID = "F-D0047-091"
TZ_TPE = ZoneInfo("Asia/Taipei")


def fetch_pop3h(
    location_name: str,
    api_key: str | None = None,
    now: datetime | None = None,
    cache_minutes: int = 30,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    data_id: str = DATAID,
    include_wind_speed: bool = False,
) -> dict[str, Any]:
    now = now or datetime.now(tz=TZ_TPE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_TPE)
    cache_suffix = "extended" if include_wind_speed else "pop3h"
    cache_path = Path(project_root) / "data" / "cache" / f"cwa_{cache_suffix}_{_safe_name(location_name)}_{data_id}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - float(cached.get("_cached_at", 0)) < cache_minutes * 60:
            return _current_next(cached["payload"], now)
    key = api_key or load_api_key()
    if not key:
        return _unavailable(location_name, "missing CWA_API_KEY")
    try:
        resp = requests.get(
            f"{BASE_URL}/{data_id}",
            params={
                "Authorization": key,
                "format": "JSON",
                "locationName": location_name,
                "elementName": "PoP3h,WindSpeed" if include_wind_speed else "PoP3h",
            },
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        records = _parse_records(resp.json(), location_name)
        payload = {
            "available": bool(records),
            "data_id": data_id,
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
    rows_by_time: dict[tuple[str, str], dict[str, Any]] = {}
    for elem in loc.get("WeatherElement", []):
        element_name = str(elem.get("ElementName", ""))
        for item in elem.get("Time", []):
            start_time = datetime.fromisoformat(item["StartTime"]).astimezone(TZ_TPE).isoformat()
            end_time = datetime.fromisoformat(item["EndTime"]).astimezone(TZ_TPE).isoformat()
            row = rows_by_time.setdefault(
                (start_time, end_time),
                {"start_time": start_time, "end_time": end_time, "pop": None, "wind_speed_mps": None},
            )
            value = item.get("ElementValue", [{}])[0]
            if element_name in {"PoP3h", "ProbabilityOfPrecipitation", "3小時降雨機率"}:
                raw_pop = value.get("ProbabilityOfPrecipitation") or value.get("PoP3h") or value.get("Value") or 0
                pop = _to_float(raw_pop)
                if pop is not None:
                    if pop > 1.0:
                        pop /= 100.0
                    row["pop"] = min(max(pop, 0.0), 1.0)
            if element_name in {"WindSpeed", "風速"}:
                raw_wind = value.get("WindSpeed") or value.get("Value")
                row["wind_speed_mps"] = _to_float(raw_wind)
    return sorted(rows_by_time.values(), key=lambda item: item["start_time"])


def _current_next(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    records = payload.get("records", [])
    current = None
    next_value = None
    for idx, record in enumerate(records):
        start = datetime.fromisoformat(record["start_time"]).astimezone(TZ_TPE)
        end = datetime.fromisoformat(record["end_time"]).astimezone(TZ_TPE)
        if start <= now < end and record.get("pop") is not None:
            current = float(record["pop"])
            next_pop = records[idx + 1].get("pop") if idx + 1 < len(records) else current
            next_value = float(next_pop) if next_pop is not None else current
            break
    pop_records = [record for record in records if record.get("pop") is not None]
    if current is None and pop_records:
        current = float(pop_records[0]["pop"])
        next_value = float(pop_records[1]["pop"]) if len(pop_records) > 1 else current
    return {
        "available": bool(payload.get("available", False) and current is not None),
        "data_id": payload.get("data_id"),
        "location_name": payload.get("location_name"),
        "current": current,
        "next": next_value,
        "current_wind_speed_mps": _window_value(records, now, "wind_speed_mps", fallback_index=0),
        "next_wind_speed_mps": _next_window_value(records, now, "wind_speed_mps"),
        "records": records,
        "fetched_at": payload.get("fetched_at"),
    }


def _unavailable(location_name: str, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "data_id": None,
        "location_name": location_name,
        "current": None,
        "next": None,
        "current_wind_speed_mps": None,
        "next_wind_speed_mps": None,
        "records": [],
        "fetched_at": None,
        "reason": reason,
    }


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _window_value(records: list[dict[str, Any]], now: datetime, key: str, fallback_index: int = 0) -> float | None:
    for record in records:
        start = datetime.fromisoformat(record["start_time"]).astimezone(TZ_TPE)
        end = datetime.fromisoformat(record["end_time"]).astimezone(TZ_TPE)
        if start <= now < end:
            value = record.get(key)
            return float(value) if value is not None else None
    if len(records) > fallback_index:
        value = records[fallback_index].get(key)
        return float(value) if value is not None else None
    return None


def _next_window_value(records: list[dict[str, Any]], now: datetime, key: str) -> float | None:
    for idx, record in enumerate(records):
        start = datetime.fromisoformat(record["start_time"]).astimezone(TZ_TPE)
        end = datetime.fromisoformat(record["end_time"]).astimezone(TZ_TPE)
        if start <= now < end:
            next_idx = min(idx + 1, len(records) - 1)
            value = records[next_idx].get(key)
            return float(value) if value is not None else None
    if len(records) > 1:
        value = records[1].get(key)
        return float(value) if value is not None else None
    return _window_value(records, now, key, fallback_index=0)
