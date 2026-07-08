from __future__ import annotations

from typing import Any


ANCHORS = ["H1", "H2", "H3", "H4"]


def blend_with_cwa_pop3h(
    rule_adjusted_probs: dict[str, float],
    cwa_pop: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    cfg = config.get("rain_postprocess", config)
    blending_cfg = cfg.get("blending", {})
    clip_cfg = cfg.get("probability_clip", {"min": 0.0, "max": 1.0})
    if not blending_cfg.get("enabled", True) or not cwa_pop.get("available", False):
        return {
            "final_probs": {key: _clip(float(value), clip_cfg) for key, value in rule_adjusted_probs.items()},
            "blending_detail": {},
            "cwa_blending_applied": False,
            "warning": "CWA PoP3h unavailable, fallback to LSTM + postprocess only.",
        }

    final = {}
    detail = {}
    for anchor in ANCHORS:
        anchor_cfg = blending_cfg.get(anchor, {"lstm_weight": 1.0, "cwa_weight": 0.0})
        lstm_weight = float(anchor_cfg.get("lstm_weight", 1.0))
        cwa_weight = float(anchor_cfg.get("cwa_weight", 0.0))
        source = str(anchor_cfg.get("cwa_source", "current"))
        cwa_value = float(cwa_pop.get(source, cwa_pop.get("current", 0.0)) or 0.0)
        lstm_value = float(rule_adjusted_probs.get(anchor, 0.0))
        final[anchor] = _clip(lstm_weight * lstm_value + cwa_weight * cwa_value, clip_cfg)
        detail[anchor] = {
            "lstm_weight": lstm_weight,
            "cwa_weight": cwa_weight,
            "cwa_source": source,
            "cwa_value": cwa_value,
            "rule_adjusted_probability": lstm_value,
        }
    applied = any(detail[anchor]["cwa_weight"] > 0 for anchor in ANCHORS)
    return {"final_probs": final, "blending_detail": detail, "cwa_blending_applied": applied}


def _clip(value: float, clip_cfg: dict[str, Any]) -> float:
    return min(max(value, float(clip_cfg.get("min", 0.0))), float(clip_cfg.get("max", 1.0)))
