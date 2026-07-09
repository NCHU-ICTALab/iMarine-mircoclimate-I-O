from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


TAIPEI = timezone(timedelta(hours=8))


def normalize_port_local_station_records(
    station_id: str,
    station_type: str,
    raw_records: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    missing_columns: list[str] = []
    for raw in raw_records:
        try:
            normalized = _normalize_one(str(station_id), str(station_type), raw)
            records.append(normalized)
        except Exception as exc:
            warnings.append(f"parse_error: {exc}")

    required = _required_columns(str(station_type))
    for column in required:
        if not records or all(record.get(column) is None for record in records):
            missing_columns.append(column)

    return {
        "station_id": str(station_id),
        "station_type": str(station_type),
        "records": records,
        "columns": sorted(records[0].keys()) if records else required,
        "normalization_status": "ok" if records and not missing_columns else "degraded" if records else "unavailable",
        "missing_columns": missing_columns,
        "warnings": warnings,
    }


def normalized_records_to_frame(normalized: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(normalized.get("records", []))


def _normalize_one(station_id: str, station_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    raw_data = raw.get("raw_data") if isinstance(raw.get("raw_data"), dict) else raw
    timestamp = _time_value(raw, ["timestamp", "obs_time", "observed_at", "time", "LastData_DT"])
    fetched_at = _time_value(raw, ["fetched_at"]) or datetime.now(TAIPEI).isoformat(timespec="seconds")
    base = {
        "timestamp": timestamp,
        "obs_time": timestamp,
        "station_id": station_id,
        "station_type": station_type,
        "source": raw.get("source", "twport"),
        "quality_flag": raw.get("quality_flag", "ok"),
        "fetched_at": fetched_at,
    }
    if station_type == "wind":
        wind_speed, speed_meta = _speed(raw_data, ["wind_speed", "wind_speed_mps", "WS_AVG"])
        wind_gust, gust_meta = _speed(raw_data, ["wind_gust", "wind_gust_mps", "WS_MAX"])
        direction = _float_first(raw_data, ["wind_direction", "wind_direction_deg", "WD_AVG"])
        return {
            **base,
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "wind_direction": direction,
            "wind_gust_direction": _float_first(raw_data, ["wind_gust_direction", "wind_gust_direction_deg", "WD_MAX"]),
            "raw_station_ref": raw.get("raw_station_ref"),
            "raw_wind_speed": _raw_first(raw_data, ["wind_speed", "wind_speed_mps", "WS_AVG"]),
            "raw_wind_gust": _raw_first(raw_data, ["wind_gust", "wind_gust_mps", "WS_MAX"]),
            "raw_wind_direction": _raw_first(raw_data, ["wind_direction", "wind_direction_deg", "WD_AVG"]),
            "raw_wind_gust_direction": _raw_first(raw_data, ["wind_gust_direction", "wind_gust_direction_deg", "WD_MAX"]),
            "unit_conversion_applied": bool(speed_meta["converted"] or gust_meta["converted"]),
            "original_unit": speed_meta["original_unit"] or gust_meta["original_unit"],
            "normalized_unit": "m/s",
        }
    if station_type == "tide":
        tide, meta = _length(raw_data, ["tide_level_cm", "tide_level", "TideValue", "Tide_Value"], target_unit="cm")
        return {
            **base,
            "tide_level_cm": tide,
            "tide_level": tide,
            "tide_reference": raw_data.get("tide_reference"),
            "raw_tide_level": _raw_first(raw_data, ["tide_level_cm", "tide_level", "TideValue", "Tide_Value"]),
            "unit_conversion_applied": meta["converted"],
            "original_unit": meta["original_unit"],
            "normalized_unit": "cm",
        }
    wave_height, wave_meta = _length(raw_data, ["wave_height_m", "wave_height", "Hs"], target_unit="m")
    return {
        **base,
        "wave_height_m": wave_height,
        "wave_period_s": _float_first(raw_data, ["wave_period_s", "wave_period", "Tp"]),
        "current_speed": _float_first(raw_data, ["current_speed", "current_speed_mps", "Velocity", "ADCP_Velocity"]),
        "current_direction": _float_first(raw_data, ["current_direction", "current_direction_deg", "Vmdir", "ADCP_Vmdir"]),
        "marine_reference": raw_data.get("marine_reference"),
        "raw_wave_height": _raw_first(raw_data, ["wave_height_m", "wave_height", "Hs"]),
        "raw_wave_period": _raw_first(raw_data, ["wave_period_s", "wave_period", "Tp"]),
        "raw_current_speed": _raw_first(raw_data, ["current_speed", "current_speed_mps", "Velocity", "ADCP_Velocity"]),
        "raw_current_direction": _raw_first(raw_data, ["current_direction", "current_direction_deg", "Vmdir", "ADCP_Vmdir"]),
        "unit_conversion_applied": wave_meta["converted"],
        "original_unit": wave_meta["original_unit"],
        "normalized_unit": "m",
    }


def _required_columns(station_type: str) -> list[str]:
    if station_type == "wind":
        return ["timestamp", "obs_time", "station_id", "station_type", "source", "wind_speed", "wind_gust", "wind_direction", "quality_flag", "fetched_at"]
    if station_type == "tide":
        return ["timestamp", "obs_time", "station_id", "station_type", "source", "tide_level_cm", "quality_flag", "fetched_at"]
    return ["timestamp", "obs_time", "station_id", "station_type", "source", "wave_height_m", "wave_period_s", "current_speed", "current_direction", "quality_flag", "fetched_at"]


def _time_value(raw: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(TAIPEI)
        return parsed.isoformat()
    return None


def _raw_first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in raw:
            return raw.get(key)
    return None


def _float_first(raw: dict[str, Any], keys: list[str]) -> float | None:
    value = _raw_first(raw, keys)
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _unit(raw: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        if key in raw and raw.get(key):
            return str(raw[key]).lower()
    return default


def _speed(raw: dict[str, Any], keys: list[str]) -> tuple[float | None, dict[str, Any]]:
    value = _float_first(raw, keys)
    unit = _unit(raw, ["wind_unit", "speed_unit", "unit"], "m/s")
    converted = False
    if value is None:
        return None, {"converted": False, "original_unit": None}
    if unit in {"knot", "knots", "kt"}:
        value *= 0.514444
        converted = True
    elif unit in {"km/h", "kmh", "kph"}:
        value /= 3.6
        converted = True
    return round(float(value), 6), {"converted": converted, "original_unit": unit if converted else None}


def _length(raw: dict[str, Any], keys: list[str], target_unit: str) -> tuple[float | None, dict[str, Any]]:
    value = _float_first(raw, keys)
    unit = _unit(raw, ["tide_unit", "wave_unit", "length_unit", "unit"], target_unit)
    converted = False
    if value is None:
        return None, {"converted": False, "original_unit": None}
    if target_unit == "cm" and unit == "m":
        value *= 100
        converted = True
    elif target_unit == "m" and unit == "cm":
        value /= 100
        converted = True
    return round(float(value), 6), {"converted": converted, "original_unit": unit if converted else None}
