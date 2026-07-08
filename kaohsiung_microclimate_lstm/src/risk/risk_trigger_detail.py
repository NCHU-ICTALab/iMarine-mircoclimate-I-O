from __future__ import annotations

from typing import Any

from .level_mapping import LEVEL_ORDER


LOW_RELIABILITY = {"low", "low_to_medium", "optional", "reference_only", "low_confidence", "unavailable"}


def build_risk_trigger_detail(
    dispatch_risk_level: str,
    rain_level: str,
    wind_level: str,
    gust_level: str,
    visibility_level: str | None,
    tide_level: str | None,
    reliability: dict[str, str],
    trigger_priority: list[str] | None = None,
) -> dict[str, Any]:
    if dispatch_risk_level == "normal":
        return {
            "primary_trigger": "none",
            "primary_trigger_level": "normal",
            "primary_trigger_reliability": None,
            "all_trigger_levels": {
                "rain": rain_level,
                "wind_speed": wind_level,
                "wind_gust": gust_level,
                "visibility": visibility_level,
                "tide": tide_level,
            },
            "is_low_reliability_trigger": False,
        }
    levels = {
        "rain_probability": rain_level,
        "wind_speed": wind_level,
        "wind_gust": gust_level,
        "visibility": visibility_level,
        "tide": tide_level,
    }
    priority = trigger_priority or ["wind_gust", "wind_speed", "rain_probability", "visibility", "tide"]
    max_score = max((LEVEL_ORDER.get(level, -1) for level in levels.values() if level is not None), default=0)
    target_score = LEVEL_ORDER.get(dispatch_risk_level, max_score)
    candidates = [name for name in priority if LEVEL_ORDER.get(levels.get(name), -1) == target_score]
    primary = candidates[0] if candidates else "unknown"
    primary_reliability = reliability.get(primary) if primary != "unknown" else None
    return {
        "primary_trigger": primary,
        "primary_trigger_level": levels.get(primary, dispatch_risk_level),
        "primary_trigger_reliability": primary_reliability,
        "all_trigger_levels": {
            "rain": rain_level,
            "wind_speed": wind_level,
            "wind_gust": gust_level,
            "visibility": visibility_level,
            "tide": tide_level,
        },
        "is_low_reliability_trigger": primary_reliability in LOW_RELIABILITY,
    }


def is_risk_above_normal(level: str) -> bool:
    return LEVEL_ORDER.get(level, 0) > LEVEL_ORDER["normal"]
