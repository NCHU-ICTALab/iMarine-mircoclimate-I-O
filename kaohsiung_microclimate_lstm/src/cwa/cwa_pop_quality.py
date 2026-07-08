from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TZ_TPE = ZoneInfo("Asia/Taipei")


def parse_cwa_pop_value(raw_value: Any) -> dict[str, Any]:
    if raw_value is None:
        return _invalid(raw_value, "not_available", "CWA PoP value is not available.")
    if raw_value == "":
        return _invalid(raw_value, "missing_field", "CWA PoP field is empty.")
    text = str(raw_value).strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        return _invalid(raw_value, "parse_error", "PoP value could not be parsed as numeric probability.")
    if 0.0 <= value <= 1.0:
        normalized = value
    elif 0.0 <= value <= 100.0:
        normalized = value / 100.0
    else:
        return _invalid(raw_value, "out_of_range", "PoP value is outside 0-100 percent or 0-1 probability range.")
    return {
        "available": True,
        "raw_value": raw_value,
        "normalized_value": max(0.0, min(1.0, normalized)),
        "parse_status": "ok",
        "quality_status": "valid",
        "reason": None,
    }


def build_anchor_cwa_pop_quality(
    anchor_label: str,
    anchor_time: Any,
    matched_forecast_period: dict[str, Any] | None,
    raw_pop_value: Any,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    anchor_dt = _to_taipei(anchor_time)
    source = {
        "dataset_id": source_metadata.get("dataset_id"),
        "location_name": source_metadata.get("location_name"),
        "element_name": source_metadata.get("element_name"),
        "source_resolution": source_metadata.get("source_resolution"),
    }
    if matched_forecast_period is None:
        parsed = parse_cwa_pop_value(None)
        return {
            "anchor": anchor_label,
            "anchor_time": anchor_dt.isoformat(),
            **parsed,
            "alignment_status": "no_matching_forecast_period",
            "reason": "No CWA forecast period matched this anchor time.",
            "source": source,
        }
    parsed = parse_cwa_pop_value(raw_pop_value)
    return {
        "anchor": anchor_label,
        "anchor_time": anchor_dt.isoformat(),
        **parsed,
        "alignment_status": "matched_forecast_period",
        "source": source,
    }


def align_cwa_pop_quality_to_anchors(
    cwa_timeseries: list[dict[str, Any]],
    generated_at: datetime,
    anchors: dict[str, int],
    source_metadata: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=TZ_TPE)
    if not cwa_timeseries:
        return {
            label: {
                "anchor": label,
                "anchor_time": (generated_at + _minutes(offset)).isoformat(),
                **parse_cwa_pop_value(None),
                "alignment_status": "no_forecast_timeseries",
                "reason": "CWA forecast timeseries is empty.",
                "source": {
                    "dataset_id": source_metadata.get("dataset_id"),
                    "location_name": source_metadata.get("location_name"),
                    "element_name": source_metadata.get("element_name"),
                    "source_resolution": source_metadata.get("source_resolution"),
                },
            }
            for label, offset in anchors.items()
        }

    periods = []
    for row in cwa_timeseries:
        try:
            start = datetime.fromisoformat(row["start_time"]).astimezone(TZ_TPE)
            end = datetime.fromisoformat(row["end_time"]).astimezone(TZ_TPE)
        except Exception:
            continue
        if end <= start:
            continue
        periods.append((start, end, row))

    result: dict[str, dict[str, Any]] = {}
    for label, offset in anchors.items():
        anchor_time = generated_at + _minutes(offset)
        match = next((row for start, end, row in periods if start <= anchor_time < end), None)
        raw = match.get("raw_value", match.get("pop")) if match else None
        result[label] = build_anchor_cwa_pop_quality(label, anchor_time, match, raw, source_metadata)
    return result


def _invalid(raw_value: Any, parse_status: str, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "raw_value": raw_value,
        "normalized_value": None,
        "parse_status": parse_status,
        "quality_status": "invalid",
        "reason": reason,
    }


def _to_taipei(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_TPE)
    return dt.astimezone(TZ_TPE)


def _minutes(offset: int):
    from datetime import timedelta

    return timedelta(minutes=int(offset))
