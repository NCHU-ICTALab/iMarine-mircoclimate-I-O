from __future__ import annotations

from typing import Any


FALLBACK_CHAIN = [
    "port_local_model",
    "port_local_postprocess",
    "nearby_cwa_historical_model",
    "fallback_baseline",
]


def select_prediction_mode(context: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministically select dispatch risk prediction mode.
    """
    blocking: dict[str, list[str]] = {}
    evaluated: list[dict[str, Any]] = []

    port_local_model_reasons = _port_local_model_reasons(context)
    port_local_model_eligible = not port_local_model_reasons
    evaluated.append(_mode("port_local_model", port_local_model_eligible, port_local_model_reasons))
    if port_local_model_eligible:
        return _result("port_local_model", "Port-local model passed all acceptance thresholds.", evaluated, blocking, context)
    blocking["port_local_model"] = port_local_model_reasons

    postprocess_reasons = _postprocess_reasons(context)
    postprocess_eligible = not postprocess_reasons
    evaluated.append(_mode("port_local_postprocess", postprocess_eligible, postprocess_reasons or ["VALID_KHWD_REALTIME_AVAILABLE"]))
    if postprocess_eligible:
        if bool(context.get("nearby_cwa_historical_model_available")) and bool(context.get("nearby_cwa_historical_model_accepted")):
            evaluated.append(
                _mode(
                    "nearby_cwa_historical_model",
                    True,
                    ["MODEL_AVAILABLE", "MODEL_ACCEPTED", "NOT_SELECTED_BECAUSE_KHWD_REALTIME_HAS_PRIORITY"],
                    selected=False,
                )
            )
        evaluated.append(_mode("fallback_baseline", bool(context.get("fallback_baseline_available", True)), ["NOT_SELECTED_BECAUSE_HIGHER_PRIORITY_MODE_AVAILABLE"], selected=False))
        return _result(
            "port_local_postprocess",
            "KHWD realtime data is available, so port_local_postprocess is preferred over nearby CWA historical model.",
            evaluated,
            blocking,
            context,
        )
    blocking["port_local_postprocess"] = postprocess_reasons

    nearby_reasons = _nearby_reasons(context)
    nearby_eligible = not nearby_reasons
    evaluated.append(_mode("nearby_cwa_historical_model", nearby_eligible, nearby_reasons or ["MODEL_AVAILABLE", "MODEL_ACCEPTED", "ALL_SELECTED_STATIONS_CLOSER_THAN_467441"]))
    if nearby_eligible:
        evaluated.append(_mode("fallback_baseline", bool(context.get("fallback_baseline_available", True)), ["NOT_SELECTED_BECAUSE_NEARBY_CWA_MODEL_AVAILABLE"], selected=False))
        return _result(
            "nearby_cwa_historical_model",
            "KHWD realtime unavailable; nearby CWA historical model accepted and all selected stations are closer than 467441.",
            evaluated,
            blocking,
            context,
        )
    blocking["nearby_cwa_historical_model"] = nearby_reasons

    fallback_available = bool(context.get("fallback_baseline_available", True))
    evaluated.append(_mode("fallback_baseline", fallback_available, [] if fallback_available else ["FALLBACK_BASELINE_UNAVAILABLE"]))
    return _result(
        "fallback_baseline",
        "No accepted port-local or nearby CWA model is available; using 467441 fallback baseline.",
        evaluated,
        blocking,
        context,
    )


def _port_local_model_reasons(context: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not bool(context.get("dataset_ready")):
        reasons.append("DATASET_NOT_READY")
    if not bool(context.get("port_local_model_trained")):
        reasons.append("PORT_LOCAL_MODEL_NOT_TRAINED")
    if not bool(context.get("port_local_model_available")):
        reasons.append("PORT_LOCAL_MODEL_UNAVAILABLE")
    if not bool(context.get("port_local_model_accepted")):
        reasons.append("PORT_LOCAL_MODEL_NOT_ACCEPTED")
    if int(context.get("port_local_model_critical_under_warning_count") or 0) > 0:
        reasons.append("CRITICAL_UNDER_WARNING_COUNT_GT_0")
    return reasons


def _postprocess_reasons(context: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if bool(context.get("no_realtime_khwd_mode")):
        reasons.append("KHWD_REALTIME_DISABLED_BY_REQUEST")
    if not bool(context.get("khwd_realtime_available")):
        reasons.append("KHWD_REALTIME_UNAVAILABLE")
    if int(context.get("valid_khwd_station_count") or 0) < 2:
        reasons.append("VALID_KHWD_STATION_COUNT_LT_2")
    return reasons


def _nearby_reasons(context: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not bool(context.get("nearby_cwa_historical_training_enabled", True)):
        reasons.append("NEARBY_CWA_TRAINING_DISABLED")
    if not bool(context.get("nearby_cwa_historical_model_available")):
        reasons.append("NEARBY_CWA_MODEL_UNAVAILABLE")
    if not bool(context.get("nearby_cwa_historical_model_accepted")):
        reasons.append("NEARBY_CWA_MODEL_NOT_ACCEPTED")
    if not bool(context.get("all_nearby_cwa_stations_closer_than_467441")):
        reasons.append("NEARBY_CWA_STATIONS_NOT_ALL_CLOSER_THAN_467441")
    if bool(context.get("nearby_cwa_used_as_port_local_core")):
        reasons.append("NEARBY_CWA_USED_AS_PORT_LOCAL_CORE")
    if int(context.get("nearby_cwa_critical_under_warning_count") or 0) > 0:
        reasons.append("CRITICAL_UNDER_WARNING_COUNT_GT_0")
    return reasons


def _mode(mode: str, eligible: bool, reason_codes: list[str], selected: bool | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"mode": mode, "eligible": bool(eligible), "reason_codes": reason_codes}
    if selected is not None:
        item["selected"] = bool(selected)
    return item


def _result(mode: str, reason: str, evaluated: list[dict[str, Any]], blocking: dict[str, list[str]], context: dict[str, Any]) -> dict[str, Any]:
    for item in evaluated:
        item.setdefault("selected", item["mode"] == mode)
    assertions = {
        "khwd_realtime_overrides_nearby_cwa_historical": not (
            bool(context.get("khwd_realtime_available"))
            and int(context.get("valid_khwd_station_count") or 0) >= 2
            and not bool(context.get("no_realtime_khwd_mode"))
            and mode == "nearby_cwa_historical_model"
        ),
        "nearby_cwa_only_used_when_khwd_unavailable": not (
            mode == "nearby_cwa_historical_model"
            and bool(context.get("khwd_realtime_available"))
            and not bool(context.get("no_realtime_khwd_mode"))
        ),
        "no_core_station_role_violation": not bool(context.get("nearby_cwa_used_as_port_local_core")) and not bool(context.get("467441_used_as_core_station")),
        "rain_probability_preserved_in_all_anchors": bool(context.get("rain_probability_preserved", True)),
        "cwa_pop_zero_is_valid_probability": bool(context.get("cwa_pop_zero_is_valid_probability", True)),
        "critical_under_warning_blocks_model_activation": int(context.get("port_local_model_critical_under_warning_count") or 0) <= 0 or mode != "port_local_model",
        "station_usage_exported_to_ui": bool(context.get("station_usage_exported_to_ui", True)),
        "model_training_status_exported_to_ui": bool(context.get("model_training_status_exported_to_ui", True)),
    }
    return {
        "selected_mode": mode,
        "fallback_chain": list(FALLBACK_CHAIN),
        "fallback_to_nearby_cwa_historical_model": mode == "nearby_cwa_historical_model",
        "fallback_to_467441": mode == "fallback_baseline",
        "selection_reason": reason,
        "evaluated_modes": evaluated,
        "blocking_reasons": blocking,
        "assertions": assertions,
        "selection_case_id": _case_id(mode, context),
    }


def _case_id(mode: str, context: dict[str, Any]) -> str:
    if mode == "port_local_model":
        return "PORT_LOCAL_MODEL_ACCEPTED"
    if mode == "port_local_postprocess" and bool(context.get("nearby_cwa_historical_model_accepted")):
        return "KHWD_REALTIME_AVAILABLE_NEARBY_ACCEPTED"
    if mode == "nearby_cwa_historical_model":
        return "KHWD_UNAVAILABLE_NEARBY_ACCEPTED"
    if mode == "fallback_baseline":
        return "KHWD_UNAVAILABLE_NEARBY_REJECTED"
    return "DEFAULT_SELECTION"
