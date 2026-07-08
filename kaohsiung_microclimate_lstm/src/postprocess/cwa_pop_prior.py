from __future__ import annotations

from typing import Any


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
    }
    if not cwa_cfg.get("enabled", True) or cwa_cfg.get("allowed_in_model_input", False):
        return {"final_probabilities": final, "source_detail": source_detail, "cwa_prior_applied": False, "trace": trace}
    if not cwa_pop or not cwa_pop.get("available", False):
        return {"final_probabilities": final, "source_detail": source_detail, "cwa_prior_applied": False, "trace": trace}

    resolution = str(cwa_pop.get("source_resolution", "unknown"))
    cap_table = cwa_cfg.get("resolution_weight_cap", {})
    resolution_cap = float(cap_table.get(resolution, cap_table.get("unknown", 0.2)))
    weight = min(float(cwa_cfg.get("max_weight", cwa_cfg.get("max_adjustment_weight", 0.2))), resolution_cap, 0.2)
    apply_anchors = set(cwa_cfg.get("apply_anchors", ["H3", "H4"]))
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
        final[anchor] = (1.0 - weight) * final[anchor] + weight * cwa_value
        trace["adjusted_anchors"].append(anchor)
        source_detail[anchor].update(
            {
                "cwa_prior_applied": True,
                "cwa_weight": weight,
                "cwa_dataset_id": cwa_pop.get("dataset_id"),
                "cwa_location_name": cwa_pop.get("location_name"),
                "cwa_element_name": cwa_pop.get("element_name"),
                "cwa_source_resolution": resolution,
                "cwa_pop_quality": quality,
            }
        )

    trace["weight"] = weight if trace["adjusted_anchors"] else 0.0
    trace["cwa_pop_used_as_postprocess_prior"] = bool(trace["adjusted_anchors"])
    return {
        "final_probabilities": final,
        "source_detail": source_detail,
        "cwa_prior_applied": bool(trace["adjusted_anchors"]),
        "trace": trace,
    }
