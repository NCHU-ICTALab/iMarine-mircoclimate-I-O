from __future__ import annotations

from typing import Any

from ..risk.level_mapping import LEVEL_ORDER, map_wind_speed_to_operation_level


def apply_port_local_wind_postprocess(
    base_wind_predictions: dict[str, str],
    port_local_wind_features: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    features = port_local_wind_features.get("features", port_local_wind_features)
    max_speed = features.get("khwd_wind_speed_max")
    station_ids = list(port_local_wind_features.get("station_ids_used", []))
    triggered = _trigger_level(max_speed, config.get("wind_speed", {}).get("thresholds_mps", {}))
    adjusted: dict[str, str] = {}
    detail: dict[str, Any] = {}
    for label, base_level in base_wind_predictions.items():
        final_level = _max_level(str(base_level), triggered)
        adjusted[label] = final_level
        detail[label] = {
            "applied": final_level != base_level,
            "source": "KHWD",
            "station_ids_used": station_ids,
            "base_operation_level": base_level,
            "adjusted_operation_level": final_level,
            "reason": _reason(max_speed, triggered, "wind speed"),
            "khwd_wind_speed_max": max_speed,
            "threshold_triggered": triggered,
        }
    return {"adjusted_predictions": adjusted, "postprocess_detail": detail}


def _trigger_level(value: Any, thresholds: dict[str, Any]) -> str | None:
    if value is None:
        return None
    numeric = float(value)
    for level in ["stop", "high_risk", "warning"]:
        threshold = thresholds.get(level)
        if threshold is not None and numeric >= float(threshold):
            return level
    return None


def _max_level(base: str, triggered: str | None) -> str:
    if triggered is None:
        return base
    return triggered if LEVEL_ORDER.get(triggered, 0) > LEVEL_ORDER.get(base, 0) else base


def _reason(value: Any, triggered: str | None, label: str) -> str:
    if value is None:
        return f"No KHWD {label} value available."
    if triggered is None:
        return f"KHWD values did not exceed {label} postprocess thresholds."
    return f"KHWD max {label} exceeded {triggered} threshold."
