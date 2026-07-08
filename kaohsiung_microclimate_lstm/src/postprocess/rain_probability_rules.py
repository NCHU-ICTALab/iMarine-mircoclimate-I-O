from __future__ import annotations

from typing import Any


ANCHORS = ["H1", "H2", "H3", "H4"]


def apply_rain_probability_rules(
    raw_probs: dict[str, float],
    nearby_precip: dict[str, Any],
    cwa_pop: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    cfg = config.get("rain_postprocess", config)
    nearby_cfg = cfg.get("nearby_precip", {})
    cwa_cfg = cfg.get("cwa_pop3h", {})
    clip_cfg = cfg.get("probability_clip", {"min": 0.0, "max": 1.0})
    probs = {key: _clip(float(raw_probs.get(key, 0.0)), clip_cfg) for key in ANCHORS}
    applied: list[dict[str, Any]] = []

    if nearby_cfg.get("enabled", True) and nearby_precip.get("available", False):
        max_1hr = float(nearby_precip.get("max_1hr", 0.0) or 0.0)
        mean_1hr = float(nearby_precip.get("mean_1hr", 0.0) or 0.0)
        if max_1hr > float(nearby_cfg.get("single_station_trigger_mm", 0.5)):
            floor = float(nearby_cfg.get("single_station_min_probability", 0.70))
            for anchor in ["H1", "H2"]:
                probs[anchor] = max(probs[anchor], floor)
            applied.append(
                {
                    "rule_id": "nearby_single_station_trigger",
                    "description": "nearby_precip_max_1hr > single_station_trigger_mm",
                    "affected_anchors": ["H1", "H2"],
                }
            )
        if mean_1hr > float(nearby_cfg.get("mean_trigger_mm", 2.0)):
            floor = float(nearby_cfg.get("mean_min_probability", 0.85))
            for anchor in ["H1", "H2"]:
                probs[anchor] = max(probs[anchor], floor)
            applied.append(
                {
                    "rule_id": "nearby_mean_trigger",
                    "description": "nearby_precip_mean_1hr > mean_trigger_mm",
                    "affected_anchors": ["H1", "H2"],
                }
            )

    if cwa_cfg.get("enabled", True) and cwa_pop.get("available", False):
        current = float(cwa_pop.get("current", 0.0) or 0.0)
        if current > float(cwa_cfg.get("high_pop_trigger", 0.60)):
            floor = current * float(cwa_cfg.get("high_pop_weight_for_rule", 0.80))
            for anchor in ANCHORS:
                probs[anchor] = max(probs[anchor], floor)
            applied.append(
                {
                    "rule_id": "cwa_high_pop_floor",
                    "description": "cwa_pop_current > high_pop_trigger",
                    "affected_anchors": list(ANCHORS),
                }
            )
        max_1hr = float(nearby_precip.get("max_1hr", 0.0) or 0.0)
        if current < float(cwa_cfg.get("low_pop_trigger", 0.10)) and max_1hr == 0.0:
            cap = float(nearby_cfg.get("dry_suppression_probability", 0.15))
            for anchor in ["H1", "H2"]:
                probs[anchor] = min(probs[anchor], cap)
            applied.append(
                {
                    "rule_id": "cwa_low_pop_dry_suppression",
                    "description": "cwa_pop_current < low_pop_trigger and nearby max rain is 0",
                    "affected_anchors": ["H1", "H2"],
                }
            )

    return {"adjusted_probs": {key: _clip(value, clip_cfg) for key, value in probs.items()}, "applied_rules": applied}


def assign_warning_levels(final_probs: dict[str, float], config: dict[str, Any]) -> dict[str, str]:
    cfg = config.get("rain_postprocess", config)
    thresholds = cfg.get("warning_thresholds", {"watch": 0.30, "warning": 0.50, "stop": 0.70})
    out = {}
    for anchor, prob in final_probs.items():
        if prob >= float(thresholds.get("stop", 0.70)):
            out[anchor] = "stop"
        elif prob >= float(thresholds.get("warning", 0.50)):
            out[anchor] = "warning"
        elif prob >= float(thresholds.get("watch", 0.30)):
            out[anchor] = "watch"
        else:
            out[anchor] = "normal"
    return out


def _clip(value: float, clip_cfg: dict[str, Any]) -> float:
    return min(max(value, float(clip_cfg.get("min", 0.0))), float(clip_cfg.get("max", 1.0)))
