from __future__ import annotations

from typing import Any


def decide_prediction_mode(
    station_availability: dict[str, Any],
    model_metrics: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    min_required = int(config.get("station_pool", {}).get("min_required_port_local_wind_stations", 2))
    available_wind = list(station_availability.get("available_port_local_wind_station_ids", []))
    available_port_local = list(station_availability.get("available_port_local_station_ids", []))
    enough_wind = len(available_wind) >= min_required
    port_model_available = bool(config.get("port_local_model", {}).get("enabled", False))
    metrics_ok = bool((model_metrics or {}).get("metrics_ok", True))
    postprocess_enabled = bool(config.get("port_local_postprocess", {}).get("enabled", True))

    if enough_wind and port_model_available and metrics_ok:
        return {
            "prediction_mode": "port_local_model",
            "reason": "Validated port-local model and enough KHWD wind stations are available.",
            "using_port_local_station": True,
            "fallback_to_467441": False,
            "fallback_reason": None,
            "port_local_model_available": True,
            "model_retraining_required": False,
        }

    if enough_wind and postprocess_enabled:
        return {
            "prediction_mode": "port_local_postprocess",
            "reason": "Port-local KHWD data is available, but no validated retrained port-local model is enabled.",
            "using_port_local_station": True,
            "fallback_to_467441": False,
            "fallback_reason": None,
            "port_local_model_available": False,
            "model_retraining_required": True,
        }

    reason = "No valid port-local KHWD station data available."
    if available_port_local and len(available_wind) < min_required:
        reason = f"Only {len(available_wind)} valid KHWD wind station(s) available; require {min_required}."
    return {
        "prediction_mode": "fallback_baseline",
        "reason": reason,
        "using_port_local_station": False,
        "fallback_to_467441": True,
        "fallback_reason": reason,
        "port_local_model_available": False,
        "model_retraining_required": True,
    }
