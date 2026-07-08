from __future__ import annotations

from typing import Any


DEFAULT_RELIABILITY = {
    "wind_speed": "high",
    "wind_gust": "medium_high",
    "rain_probability": "low_to_medium",
    "tide": "reference_only",
    "visibility": "optional",
    "marine_transfer": "low_confidence",
}


def reliability_profile(config: dict[str, Any]) -> dict[str, str]:
    profile = dict(DEFAULT_RELIABILITY)
    profile.update({k: str(v) for k, v in config.get("reliability", {}).items()})
    return profile


def confidence_for(name: str, config: dict[str, Any], default: str = "unknown") -> str:
    return reliability_profile(config).get(name, default)
