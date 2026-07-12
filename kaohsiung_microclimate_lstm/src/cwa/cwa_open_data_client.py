from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from urllib3.exceptions import InsecureRequestWarning


TZ_TPE = ZoneInfo("Asia/Taipei")
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def load_cwa_api_key(env_name: str = "CWA_API_KEY", project_root: str | Path = "kaohsiung_microclimate_lstm") -> str | None:
    if os.environ.get(env_name):
        return os.environ[env_name]
    env_path = Path(project_root) / ".env"
    if not env_path.exists():
        env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{env_name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class CwaOpenDataClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://opendata.cwa.gov.tw/api/v1/rest/datastore",
        timeout_seconds: int = 10,
        cache_minutes: int = 30,
        cache_dir: str | Path = "kaohsiung_microclimate_lstm/data/cache/cwa",
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        verify_ssl: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = int(timeout_seconds)
        self.cache_minutes = int(cache_minutes)
        self.cache_dir = Path(cache_dir)
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self.verify_ssl = bool(verify_ssl)

    def fetch_dataset(
        self,
        dataset_id: str,
        location_name: str | None = None,
        element_name: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if not self.api_key:
            return self._unavailable(dataset_id, location_name, element_name, "missing CWA_API_KEY")
        cache_path = self._cache_path(dataset_id, location_name, element_name)
        if not force_refresh and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("_cached_at", 0)) < self.cache_minutes * 60:
                return cached["payload"]

        params = {"Authorization": self.api_key, "format": "JSON"}
        if location_name:
            params["locationName"] = location_name
        if element_name:
            params["elementName"] = element_name

        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                response = requests.get(
                    f"{self.base_url}/{dataset_id}",
                    params=params,
                    timeout=self.timeout_seconds,
                    verify=self.verify_ssl,
                )
                response.raise_for_status()
                payload = {
                    "available": True,
                    "dataset_id": dataset_id,
                    "location_name": location_name,
                    "element_name": element_name,
                    "json": response.json(),
                    "fetched_at": datetime.now(tz=TZ_TPE).isoformat(timespec="seconds"),
                }
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"_cached_at": time.time(), "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
                return payload
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = _sanitize_error(str(exc), self.api_key)
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
        return self._unavailable(dataset_id, location_name, element_name, last_error or "unknown CWA API error")

    def fetch_pop_timeseries(
        self,
        dataset_id: str,
        location_name: str,
        element_name: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        payload = self.fetch_dataset(dataset_id, location_name, element_name, force_refresh)
        if not payload.get("available"):
            return {**payload, "valid_times": []}
        valid_times = extract_pop_timeseries(payload.get("json", {}), location_name, element_name)
        return {
            "available": bool(valid_times),
            "dataset_id": dataset_id,
            "location_name": location_name,
            "element_name": element_name,
            "source_resolution": infer_source_resolution(element_name, valid_times),
            "fetched_at": payload.get("fetched_at"),
            "valid_times": valid_times,
            "raw_unit": "%",
            "normalized_unit": "probability_0_1",
            **({"reason": "no matching PoP time series"} if not valid_times else {}),
        }

    def _cache_path(self, dataset_id: str, location_name: str | None, element_name: str | None) -> Path:
        safe = "_".join(_safe_token(part) for part in [dataset_id, location_name or "all", element_name or "all"])
        return self.cache_dir / f"{safe}.json"

    def _unavailable(self, dataset_id: str, location_name: str | None, element_name: str | None, reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "dataset_id": dataset_id,
            "location_name": location_name,
            "element_name": element_name,
            "fetched_at": datetime.now(tz=TZ_TPE).isoformat(timespec="seconds"),
            "reason": reason,
        }


def extract_pop_timeseries(body: dict[str, Any], location_name: str, element_name: str) -> list[dict[str, Any]]:
    locations = _iter_locations(body)
    location = next((item for item in locations if item.get("LocationName") == location_name or item.get("locationName") == location_name), None)
    if location is None and locations:
        location = locations[0]
    if not location:
        return []
    elements = location.get("WeatherElement") or location.get("weatherElement") or []
    element = next((item for item in elements if item.get("ElementName") == element_name or item.get("elementName") == element_name), None)
    if element is None and elements:
        element = next((item for item in elements if _looks_like_pop(item.get("ElementName") or item.get("elementName"))), None)
    if not element:
        return []
    rows = []
    for item in element.get("Time") or element.get("time") or []:
        start = item.get("StartTime") or item.get("startTime")
        end = item.get("EndTime") or item.get("endTime")
        raw_value = _extract_pop_raw_value(item)
        pop = _extract_pop_value(item)
        if start and end and pop is not None:
            rows.append(
                {
                    "start_time": _as_taipei_iso(start),
                    "end_time": _as_taipei_iso(end),
                    "raw_value": raw_value,
                    "pop": pop,
                }
            )
    return rows


def align_cwa_pop_to_anchors(cwa_timeseries: list[dict[str, Any]], generated_at: datetime, anchors: dict[str, int]) -> dict[str, float | None]:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=TZ_TPE)
    aligned: dict[str, float | None] = {}
    periods = [
        (
            datetime.fromisoformat(row["start_time"]).astimezone(TZ_TPE),
            datetime.fromisoformat(row["end_time"]).astimezone(TZ_TPE),
            float(row["pop"]),
        )
        for row in cwa_timeseries
    ]
    for label, offset in anchors.items():
        anchor_time = generated_at + timedelta(minutes=int(offset))
        value = next((pop for start, end, pop in periods if start <= anchor_time < end), None)
        aligned[label] = value
    return aligned


def infer_source_resolution(element_name: str | None, timeseries: list[dict[str, Any]] | None = None) -> str:
    if timeseries:
        try:
            start = datetime.fromisoformat(timeseries[0]["start_time"])
            end = datetime.fromisoformat(timeseries[0]["end_time"])
            hours = round((end - start).total_seconds() / 3600)
            return f"{hours}h" if hours in {3, 6, 12} else "unknown"
        except Exception:
            return "unknown"
    text = str(element_name or "").lower()
    if "3" in text or "pop3h" in text:
        return "3h_unverified"
    if "6" in text or "pop6h" in text:
        return "6h_unverified"
    if "12" in text or "pop12h" in text:
        return "12h_unverified"
    return "unknown"


def _iter_locations(body: dict[str, Any]) -> list[dict[str, Any]]:
    records = body.get("records", {})
    locations = records.get("Location") or records.get("location") or []
    groups = records.get("Locations") or records.get("locations") or []
    for group in groups:
        locations.extend(group.get("Location") or group.get("location") or [])
    return locations


def _extract_pop_value(item: dict[str, Any]) -> float | None:
    raw = _extract_pop_raw_value(item)
    if raw is None:
        return None
    try:
        text = str(raw).strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        pop = float(text)
    except (TypeError, ValueError):
        return None
    if pop > 1.0:
        pop /= 100.0
    return max(0.0, min(1.0, pop))


def _extract_pop_raw_value(item: dict[str, Any]) -> Any:
    values = item.get("ElementValue") or item.get("elementValue") or []
    if isinstance(values, dict):
        values = [values]
    for value in values:
        for key in ["ProbabilityOfPrecipitation", "PoP3h", "PoP6h", "PoP12h", "Value", "value"]:
            if key in value and value[key] not in [None, ""]:
                return value[key]
    return None


def _looks_like_pop(name: str | None) -> bool:
    text = str(name or "").lower()
    return "pop" in text or "降雨機率" in text or "降水機率" in text


def _as_taipei_iso(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(TZ_TPE).isoformat()


def _safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value))


def _sanitize_error(message: str, api_key: str | None) -> str:
    return message.replace(api_key, "<CWA_API_KEY>") if api_key else message
