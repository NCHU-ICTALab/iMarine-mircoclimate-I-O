from __future__ import annotations

from typing import Any


DEFAULT_CWA_POP_WEIGHTS = {
    "H1": {"own_weight": 1.0, "cwa_weight": 0.0},
    "H2": {"own_weight": 1.0, "cwa_weight": 0.0},
    "H3": {"own_weight": 0.8, "cwa_weight": 0.2},
    "H4": {"own_weight": 0.8, "cwa_weight": 0.2},
}
DEFAULT_CWA_POP_PROFILES = {
    "conservative": {
        "apply_anchors": ["H3", "H4"],
        "weights": DEFAULT_CWA_POP_WEIGHTS,
    },
    "graduated_like_wind": {
        "apply_anchors": ["H1", "H2", "H3", "H4"],
        "weights": {
            "H1": {"own_weight": 0.8, "cwa_weight": 0.2},
            "H2": {"own_weight": 0.6, "cwa_weight": 0.4},
            "H3": {"own_weight": 0.4, "cwa_weight": 0.6},
            "H4": {"own_weight": 0.2, "cwa_weight": 0.8},
        },
    },
}


def _normalize_pop(value: Any) -> float | None:
    if value is None:
        return None
    pop = float(value)
    if pop > 1.0:
        pop /= 100.0
    return max(0.0, min(1.0, pop))


def apply_cwa_pop_prior(rain_probabilities: dict[str, float], cwa_pop: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    cwa_cfg = {**config.get("cwa_pop", {}), **config.get("cwa_pop_prior", {})}
    final = {anchor: max(0.0, min(1.0, float(prob))) for anchor, prob in rain_probabilities.items()}
    source_detail = {
        anchor: {
            "model_used": True,
            "nearby_postprocess_applied": False,
            "cwa_prior_applied": False,
            "cwa_weight": 0.0,
            "cwa_dataset_id": None,
            "cwa_location_name": None,
            "cwa_source_resolution": None,
        }
        for anchor in final
    }
    trace = {
        "cwa_pop_used_as_model_input": False,
        "cwa_pop_used_as_postprocess_prior": False,
        "adjusted_anchors": [],
        "weight": 0.0,
        "weights": {},
    }
    if not cwa_cfg.get("enabled", True) or cwa_cfg.get("allowed_in_model_input", False):
        return {"final_probabilities": final, "source_detail": source_detail, "cwa_prior_applied": False, "trace": trace}
    if not cwa_pop or not cwa_pop.get("available", False):
        return {"final_probabilities": final, "source_detail": source_detail, "cwa_prior_applied": False, "trace": trace}

    resolution = str(cwa_pop.get("source_resolution", "unknown"))
    profile = _resolve_weight_profile(cwa_cfg)
    weights = _resolve_anchor_weights(cwa_cfg, profile)
    apply_anchors = set(profile.get("apply_anchors", cwa_cfg.get("apply_anchors", ["H3", "H4"])))
    trace["weight_profile"] = profile["name"]
    sources = {"H1": "current", "H2": "current", "H3": "current", "H4": "next"}
    anchor_pop = cwa_pop.get("anchor_pop", {}) if isinstance(cwa_pop.get("anchor_pop", {}), dict) else {}
    anchor_quality = cwa_pop.get("anchor_pop_quality", {}) if isinstance(cwa_pop.get("anchor_pop_quality", {}), dict) else {}
    require_quality = bool(cwa_cfg.get("require_quality_available", False))
    require_parse_ok = bool(cwa_cfg.get("require_parse_status_ok", False))
    for anchor in final:
        if anchor not in apply_anchors:
            continue
        quality = anchor_quality.get(anchor)
        if require_quality or quality is not None:
            if not quality or not bool(quality.get("available", False)):
                continue
            if require_parse_ok and quality.get("parse_status") != "ok":
                continue
            cwa_value = _normalize_pop(quality.get("normalized_value"))
        else:
            cwa_value = _normalize_pop(anchor_pop.get(anchor, cwa_pop.get(sources.get(anchor, "current"))))
        if cwa_value is None:
            continue
        anchor_weights = weights.get(anchor, DEFAULT_CWA_POP_WEIGHTS.get(anchor, {"own_weight": 1.0, "cwa_weight": 0.0}))
        own_weight = float(anchor_weights.get("own_weight", 1.0))
        cwa_weight = float(anchor_weights.get("cwa_weight", 0.0))
        final[anchor] = max(0.0, min(1.0, own_weight * final[anchor] + cwa_weight * cwa_value))
        trace["adjusted_anchors"].append(anchor)
        trace["weights"][anchor] = {"own_weight": own_weight, "cwa_weight": cwa_weight}
        source_detail[anchor].update(
            {
                "cwa_prior_applied": True,
                "own_weight": own_weight,
                "cwa_weight": cwa_weight,
                "cwa_dataset_id": cwa_pop.get("dataset_id"),
                "cwa_location_name": cwa_pop.get("location_name"),
                "cwa_element_name": cwa_pop.get("element_name"),
                "cwa_source_resolution": resolution,
                "cwa_pop_quality": quality,
            }
        )

    trace["weight"] = max((item["cwa_weight"] for item in trace["weights"].values()), default=0.0)
    trace["cwa_pop_used_as_postprocess_prior"] = bool(trace["adjusted_anchors"])
    return {
        "final_probabilities": final,
        "source_detail": source_detail,
        "cwa_prior_applied": bool(trace["adjusted_anchors"]),
        "trace": trace,
    }


def _resolve_weight_profile(cwa_cfg: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(cwa_cfg.get("weight_profile", "conservative"))
    profiles = cwa_cfg.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
    configured = profiles.get(profile_name)
    if not isinstance(configured, dict):
        configured = DEFAULT_CWA_POP_PROFILES.get(profile_name, DEFAULT_CWA_POP_PROFILES["conservative"])
    return {
        "name": profile_name if profile_name in profiles or profile_name in DEFAULT_CWA_POP_PROFILES else "conservative",
        "apply_anchors": configured.get("apply_anchors", DEFAULT_CWA_POP_PROFILES["conservative"]["apply_anchors"]),
        "weights": configured.get("weights", DEFAULT_CWA_POP_WEIGHTS),
    }


def _resolve_anchor_weights(cwa_cfg: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, dict[str, float]]:
    configured = profile.get("weights") if isinstance(profile, dict) else cwa_cfg.get("weights")
    if not isinstance(configured, dict):
        configured = DEFAULT_CWA_POP_WEIGHTS
    weights: dict[str, dict[str, float]] = {}
    for anchor, default in DEFAULT_CWA_POP_WEIGHTS.items():
        item = configured.get(anchor, default) if isinstance(configured, dict) else default
        if not isinstance(item, dict):
            item = default
        cwa_weight = float(item.get("cwa_weight", default["cwa_weight"]))
        own_weight = float(item.get("own_weight", 1.0 - cwa_weight))
        weights[anchor] = {
            "own_weight": max(0.0, min(1.0, own_weight)),
            "cwa_weight": max(0.0, min(1.0, cwa_weight)),
        }
    return weights
