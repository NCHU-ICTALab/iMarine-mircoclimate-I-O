from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import TAIPEI, UTC


def first_present(data: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in data and data[name] not in ("", None, "-"):
            return data[name]
    return None


def to_float(value: Any) -> float | None:
    if value in ("", None, "-", "NaN"):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_time(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TAIPEI)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed


def flatten_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("records", {}).get("Station"),
        payload.get("records", {}).get("location"),
        payload.get("records", {}).get("Locations", [{}])[0].get("Location")
        if isinstance(payload.get("records", {}).get("Locations"), list)
        else None,
        payload.get("data"),
        payload.get("items"),
        payload.get("result"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return [payload]


def cwa_weather_value(record: dict[str, Any], element_names: list[str]) -> Any:
    weather_elements = record.get("WeatherElement") or record.get("weatherElement") or []
    if isinstance(weather_elements, list):
        for element in weather_elements:
            if not isinstance(element, dict):
                continue
            name = element.get("ElementName") or element.get("elementName")
            if name not in element_names:
                continue
            return element.get("ElementValue") or element.get("elementValue")
    return None
