from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_KHWD_STATION_IDS = ["KHWD01", "KHWD04", "KHWD05", "KHWD06", "KHWD07", "KHWD08"]
VALUE_KEYS = ["WS_AVG", "WD_AVG", "WS_MAX", "WD_MAX", "MAX_T"]


def parse_twport_realtime_wind_records(
    document: str,
    station_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    station_ids = station_ids or DEFAULT_KHWD_STATION_IDS
    text = _to_text(document)
    candidates: dict[str, list[dict[str, Any]]] = {station_id: [] for station_id in station_ids}
    for station_id in station_ids:
        raw_refs = _raw_refs_for_station(text, station_id)
        for raw_ref in raw_refs:
            try:
                record = _parse_record_near_ref(text, station_id, raw_ref)
                if record:
                    candidates[station_id].append(record)
            except Exception:
                continue

    selected: list[dict[str, Any]] = []
    for station_id in station_ids:
        best = _select_best_record(candidates[station_id])
        if best is not None:
            selected.append(best)
    return selected


def canonical_khwd_station_id(raw_station_ref: str, station_ids: list[str] | None = None) -> str | None:
    station_ids = station_ids or DEFAULT_KHWD_STATION_IDS
    raw = str(raw_station_ref)
    return next((station_id for station_id in station_ids if raw.startswith(station_id)), None)


def _to_text(document: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", html.unescape(str(document)))
    text = text.replace("\r", "\n")
    text = re.sub(r"[;\t]+", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def _raw_refs_for_station(text: str, station_id: str) -> list[str]:
    pattern = re.compile(rf"\b({re.escape(station_id)}[A-Z0-9]*)\b")
    refs = []
    for match in pattern.finditer(text):
        ref = match.group(1)
        if ref not in refs:
            refs.append(ref)
    refs.sort(key=lambda ref: (0 if ref.endswith("M01") else 1 if ref.endswith("M10") else 2, ref))
    return refs


def _parse_record_near_ref(text: str, station_id: str, raw_ref: str) -> dict[str, Any] | None:
    positions = [match.start() for match in re.finditer(rf"\b{re.escape(raw_ref)}\b", text)]
    records = []
    for pos in positions:
        tail = text[pos : min(len(text), pos + 900)]
        next_match = re.search(rf"\b(?!{re.escape(raw_ref)}\b)KHWD\d{{2}}[A-Z0-9]*\b", tail[len(raw_ref) :])
        end = len(raw_ref) + next_match.start() if next_match else len(tail)
        window = tail[:end]
        values = _extract_values(window)
        if "WS_AVG" not in values and "WS_MAX" not in values:
            continue
        timestamp = _parse_timestamp(values.get("MAX_T") or _nearest_timestamp(window))
        quality_flag = "ok"
        if timestamp is None:
            quality_flag = "degraded"
        if "WS_MAX" not in values:
            quality_flag = "missing_gust"
        records.append(
            {
                "station_id": station_id,
                "station_type": "wind",
                "timestamp": timestamp,
                "obs_time": timestamp,
                "wind_speed": _to_float(values.get("WS_AVG")),
                "wind_direction": _to_float(values.get("WD_AVG")),
                "wind_gust": _to_float(values.get("WS_MAX")),
                "wind_gust_direction": _to_float(values.get("WD_MAX")),
                "raw_station_ref": raw_ref,
                "source": "twport_realtime_panel",
                "quality_flag": quality_flag,
                "raw_data": {
                    "WS_AVG": _to_float(values.get("WS_AVG")),
                    "WD_AVG": _to_float(values.get("WD_AVG")),
                    "WS_MAX": _to_float(values.get("WS_MAX")),
                    "WD_MAX": _to_float(values.get("WD_MAX")),
                    "MAX_T": values.get("MAX_T"),
                },
            }
        )
    return _select_best_record(records)


def _extract_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in VALUE_KEYS:
        if key == "MAX_T":
            pattern = re.compile(rf"{key}\s*=\s*([0-9]{{4}}[/-][0-9]{{1,2}}[/-][0-9]{{1,2}}(?:\s*[^\d\s]{{0,4}}\s*)?[0-9]{{1,2}}:[0-9]{{2}}(?::[0-9]{{2}})?)")
        else:
            pattern = re.compile(rf"{key}\s*=\s*(-?\d+(?:\.\d+)?)")
        match = pattern.search(text)
        if match:
            values[key] = match.group(1).strip()
    return values


def _nearest_timestamp(text: str) -> str | None:
    patterns = [
        r"\d{4}[/-]\d{1,2}[/-]\d{1,2}\s*(?:上午|下午|AM|PM|銝\?|銝\?)?\s*\d{1,2}:\d{2}(?::\d{2})?",
        r"\d{4}-\d{1,2}-\d{1,2}T\d{1,2}:\d{2}(?::\d{2})?(?:\+08:00)?",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[-1]
    return None


def _parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    meridiem = None
    if "下午" in raw or "PM" in raw.upper() or "銝?" in raw:
        meridiem = "pm"
    elif "上午" in raw or "AM" in raw.upper() or "銝?" in raw:
        meridiem = "am"
    cleaned = re.sub(r"(上午|下午|AM|PM|銝\?|銝\?)", " ", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parsed = pd.to_datetime(cleaned, errors="coerce")
    if pd.isna(parsed):
        return None
    dt = parsed.to_pydatetime()
    if meridiem == "pm" and dt.hour < 12:
        dt = dt.replace(hour=dt.hour + 12)
    elif meridiem == "am" and dt.hour == 12:
        dt = dt.replace(hour=0)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TAIPEI)
    return dt.astimezone(TAIPEI).isoformat(timespec="seconds")


def _select_best_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None

    def key(record: dict[str, Any]) -> tuple[datetime, int]:
        ts = pd.to_datetime(record.get("timestamp"), errors="coerce")
        if pd.isna(ts):
            dt = datetime.min.replace(tzinfo=TAIPEI)
        else:
            dt = ts.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
        completeness = sum(record.get(name) is not None for name in ["wind_speed", "wind_direction", "wind_gust", "wind_gust_direction"])
        return dt, completeness

    return max(records, key=key)


def _to_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None
