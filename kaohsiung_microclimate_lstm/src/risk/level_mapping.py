from __future__ import annotations

from typing import Any

try:
    from .beaufort_scale import map_mps_to_beaufort
except ImportError:  # pragma: no cover
    from beaufort_scale import map_mps_to_beaufort


LEVEL_ORDER = {
    "normal": 0,
    "watch": 1,
    "warning": 2,
    "high_risk": 3,
    "stop": 4,
}


def _thresholds(config: dict[str, Any], key: str) -> dict[str, float]:
    nested = config.get("dispatch_thresholds", {}).get(key, {})
    if key == "wind_speed_mps":
        nested = {**nested, **config.get("wind_speed", {}).get("thresholds_mps", {})}
    if key == "wind_gust_mps":
        nested = {**nested, **config.get("wind_gust", {}).get("thresholds_mps", {})}
    return {k: float(v) for k, v in nested.items() if isinstance(v, (int, float))}


def map_rain_probability_to_level(probability: float, config: dict[str, Any]) -> str:
    thresholds = _thresholds(config, "rain_probability")
    watch = thresholds.get("watch", thresholds.get("normal", 0.30))
    warning = thresholds.get("warning", thresholds.get("watch", 0.50))
    high_risk = thresholds.get("high_risk", thresholds.get("warning", 0.70))
    prob = max(0.0, min(1.0, float(probability)))
    if prob >= high_risk:
        return "high_risk"
    if prob >= warning:
        return "warning"
    if prob >= watch:
        return "watch"
    return "normal"


def map_wind_speed_to_level(wind_speed_mps: float, config: dict[str, Any]) -> str:
    thresholds = _thresholds(config, "wind_speed_mps")
    value = float(wind_speed_mps)
    if value >= thresholds.get("stop", 17.2):
        return "stop"
    if value >= thresholds.get("high_risk", 13.9):
        return "high_risk"
    if value >= thresholds.get("warning", 10.8):
        return "warning"
    if value >= thresholds.get("watch", 8.0):
        return "watch"
    return "normal"


def map_wind_gust_to_level(wind_gust_mps: float, config: dict[str, Any], use_buffer: bool = True) -> str:
    thresholds = _thresholds(config, "wind_gust_mps")
    buffer = float(config.get("wind_gust", {}).get("uncertainty_buffer_mps", 1.2)) if use_buffer else 0.0
    value = float(wind_gust_mps) + buffer
    if value >= thresholds.get("stop", 20.8):
        return "stop"
    if value >= thresholds.get("high_risk", 17.2):
        return "high_risk"
    if value >= thresholds.get("warning", 13.9):
        return "warning"
    if value >= thresholds.get("watch", 10.8):
        return "watch"
    return "normal"


OPERATION_LABELS = {
    "normal": "一般風險",
    "watch": "注意風況",
    "warning": "限制高風險作業",
    "high_risk": "延後高風險作業",
    "stop": "停止暴露作業",
}


def map_wind_speed_to_operation_level(wind_speed_mps: float, config: dict[str, Any]) -> dict[str, Any]:
    level = map_wind_speed_to_level(wind_speed_mps, config)
    return {
        "operation_level": level,
        "operation_label": OPERATION_LABELS[level],
        "threshold_basis": "wind_speed_mps",
        "beaufort": map_mps_to_beaufort(wind_speed_mps),
    }


def map_wind_gust_to_operation_level(wind_gust_mps: float, config: dict[str, Any], use_buffer: bool = True) -> dict[str, Any]:
    original = map_wind_gust_to_level(wind_gust_mps, config, use_buffer=False)
    final = map_wind_gust_to_level(wind_gust_mps, config, use_buffer=use_buffer)
    buffer = float(config.get("wind_gust", {}).get("uncertainty_buffer_mps", 1.2)) if use_buffer else 0.0
    return {
        "operation_level": final,
        "operation_label": OPERATION_LABELS[final],
        "threshold_basis": "wind_gust_mps",
        "buffer_applied": bool(use_buffer and final != original),
        "buffer_mps": buffer,
        "original_level_without_buffer": original,
        "beaufort": map_mps_to_beaufort(wind_gust_mps),
    }
