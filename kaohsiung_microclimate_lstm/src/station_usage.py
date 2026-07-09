from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_KHWD_IDS = ["KHWD01", "KHWD04", "KHWD05", "KHWD06", "KHWD07", "KHWD08"]
DEFAULT_NEARBY_IDS = ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"]


def build_current_station_usage(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    mode = str(result.get("prediction_mode", "fallback_baseline"))
    trace = result.get("trace", {})
    port_ids = list(trace.get("port_local_station_ids_used") or _port_local_ids_from_result(result) or DEFAULT_KHWD_IDS)
    nearby_ids = list(trace.get("nearby_cwa_selected_station_ids") or result.get("nearby_cwa_historical_summary", {}).get("selected_station_ids") or DEFAULT_NEARBY_IDS)
    baseline_id = str(config.get("fallback_baseline", {}).get("station_id", "467441"))
    if mode in {"port_local_postprocess", "port_local_model"}:
        used_port = port_ids
        used_nearby: list[str] = []
        baseline_used = False
        wind_source = "KHWD" if mode == "port_local_postprocess" else "port_local_model"
        gust_source = wind_source
    elif mode == "nearby_cwa_historical_model":
        used_port = []
        used_nearby = nearby_ids
        baseline_used = False
        wind_source = "nearby_cwa_historical_model"
        gust_source = "nearby_cwa_historical_model"
    else:
        used_port = []
        used_nearby = []
        baseline_used = True
        wind_source = "467441_fallback_baseline"
        gust_source = "467441_fallback_baseline"
    return {
        "selected_prediction_mode": mode,
        "active_wind_source": wind_source,
        "active_gust_source": gust_source,
        "active_rain_source": "nearby_cwa_historical_rain_model_plus_cwa_prior" if bool(result.get("nearby_cwa_historical_summary", {}).get("model_accepted", False)) else "existing_rain_model_plus_cwa_prior",
        "port_local_station_ids_used": used_port,
        "nearby_cwa_station_ids_available": nearby_ids,
        "nearby_cwa_station_ids_used_for_current_prediction": used_nearby,
        "baseline_station_id": baseline_id,
        "baseline_station_used_for_current_prediction": baseline_used,
        "cwa_pop_prior_used": True,
    }


def build_station_display_rows(result: dict[str, Any], config: dict[str, Any], project_root: str | Path) -> list[dict[str, Any]]:
    usage = result.get("current_station_usage") or build_current_station_usage(result, config)
    mode = usage["selected_prediction_mode"]
    port_ids = list(usage.get("port_local_station_ids_used") or DEFAULT_KHWD_IDS)
    all_port_ids = _configured_khwd_ids(config) or DEFAULT_KHWD_IDS
    nearby_ids = list(usage.get("nearby_cwa_station_ids_available") or DEFAULT_NEARBY_IDS)
    baseline_id = str(usage.get("baseline_station_id", "467441"))
    rows: list[dict[str, Any]] = []
    for station_id in all_port_ids:
        rows.append(
            {
                "station_id": station_id,
                "station_name": _station_name(config, station_id, f"Kaohsiung Port Wind Station {station_id[-2:]}"),
                "station_group": "KHWD",
                "role": "port_local_realtime_core",
                "data_type": ["wind_speed", "wind_gust"],
                "used_for_current_prediction": station_id in port_ids and mode in {"port_local_postprocess", "port_local_model"},
                "is_port_local_core": True,
                "is_fallback_reference": False,
                "is_baseline_station": False,
            }
        )
    for station_id in nearby_ids:
        rows.append(
            {
                "station_id": station_id,
                "station_name": _station_name(config, station_id, station_id),
                "station_group": "nearby_cwa",
                "role": "nearby_cwa_historical_fallback_reference",
                "data_type": ["wind_speed", "wind_gust", "rain"],
                "used_for_current_prediction": station_id in usage.get("nearby_cwa_station_ids_used_for_current_prediction", []),
                "is_port_local_core": False,
                "is_fallback_reference": True,
                "is_baseline_station": False,
            }
        )
    rows.append(
        {
            "station_id": baseline_id,
            "station_name": config.get("fallback_baseline_station", {}).get("name", "CWA Kaohsiung Weather Station"),
            "station_group": "cwa_baseline",
            "role": "fallback_baseline_only",
            "data_type": ["wind_speed", "wind_gust", "rain_reference"],
            "used_for_current_prediction": bool(usage.get("baseline_station_used_for_current_prediction", False)),
            "is_port_local_core": False,
            "is_fallback_reference": True,
            "is_baseline_station": True,
        }
    )
    return rows


def station_role_violations(rows: list[dict[str, Any]], result: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for row in rows:
        station_id = str(row.get("station_id"))
        group = str(row.get("station_group"))
        if station_id == "467441" and bool(row.get("is_port_local_core", False)):
            violations.append("467441_must_not_be_port_local_core")
        if group == "nearby_cwa" and bool(row.get("is_port_local_core", False)):
            violations.append(f"{station_id}_nearby_cwa_must_not_be_port_local_core")
        if group == "KHWD" and row.get("used_for_current_prediction") and result.get("prediction_mode") not in {"port_local_postprocess", "port_local_model"}:
            violations.append(f"{station_id}_khwd_used_in_non_port_local_mode")
        if group == "nearby_cwa" and row.get("used_for_current_prediction") and result.get("prediction_mode") != "nearby_cwa_historical_model":
            violations.append(f"{station_id}_nearby_used_in_wrong_mode")
        if station_id == "467441" and row.get("used_for_current_prediction") and result.get("prediction_mode") != "fallback_baseline":
            violations.append("467441_used_outside_fallback_baseline")
    return violations


def _port_local_ids_from_result(result: dict[str, Any]) -> list[str]:
    summary = result.get("station_priority_summary", {})
    ids = summary.get("port_local_station_ids")
    if ids:
        return list(ids)
    for anchor in result.get("forecast_anchors", []):
        pp = anchor.get("port_local_postprocess", {})
        ids = pp.get("port_local_wind_station_ids_used") or pp.get("port_local_station_ids_used")
        if ids:
            return list(ids)
    return []


def _configured_khwd_ids(config: dict[str, Any]) -> list[str]:
    return list(config.get("port_local_data_acquisition", {}).get("station_types", {}).get("wind", {}).get("station_ids", []))


def _station_name(config: dict[str, Any], station_id: str, default: str) -> str:
    for groups in config.get("nearby_cwa_historical_station_pool", {}).values():
        if isinstance(groups, list):
            for item in groups:
                if str(item.get("station_id")) == station_id:
                    return str(item.get("name") or default)
    return default
