from __future__ import annotations

from typing import Any


def select_dispatch_prediction_mode(
    port_local_metrics: dict | None,
    postprocess_metrics: dict | None,
    fallback_metrics: dict | None,
    dataset_readiness: dict,
    config: dict,
) -> dict[str, Any]:
    fallback_chain = list(config.get("model_selection", {}).get("preferred_order", ["port_local_model", "port_local_postprocess", "fallback_baseline"]))
    failed_reasons: list[str] = []
    dataset_ready = bool(dataset_readiness.get("ready", False))
    if not dataset_ready:
        failed_reasons.extend(dataset_readiness.get("failed_reasons", ["dataset readiness failed"]))
    trained = bool((port_local_metrics or {}).get("port_local_model_trained", False))
    metrics_pass = False
    if dataset_ready and trained:
        metrics_pass, metric_failures = _metrics_pass_acceptance(port_local_metrics or {}, config)
        failed_reasons.extend(metric_failures)
    elif dataset_ready:
        failed_reasons.append("port_local_model not trained")

    if dataset_ready and trained and metrics_pass:
        return {
            "selected_mode": "port_local_model",
            "reason": "Port-local model passed all acceptance thresholds.",
            "selection_reason": "Port-local model passed all acceptance thresholds.",
            "fallback_chain": fallback_chain,
            "model_accepted": True,
            "port_local_model_available": True,
            "port_local_model_trained": True,
            "fallback_to_port_local_postprocess": False,
            "fallback_to_467441": False,
            "failed_reasons": failed_reasons,
        }

    postprocess_available = bool((postprocess_metrics or {}).get("available", True))
    if bool(config.get("model_selection", {}).get("allow_fallback_to_port_local_postprocess", True)) and postprocess_available:
        reason = "Dataset readiness failed; using port-local postprocess." if not dataset_ready else "Port-local model failed acceptance thresholds; using port-local postprocess."
        return {
            "selected_mode": "port_local_postprocess",
            "reason": reason,
            "selection_reason": reason,
            "fallback_chain": fallback_chain,
            "model_accepted": False,
            "port_local_model_available": trained,
            "port_local_model_trained": trained,
            "fallback_to_port_local_postprocess": True,
            "fallback_to_467441": False,
            "failed_reasons": failed_reasons,
        }

    return {
        "selected_mode": "fallback_baseline",
        "reason": "KHWD port-local postprocess unavailable; using fallback baseline.",
        "selection_reason": "KHWD port-local postprocess unavailable; using fallback baseline.",
        "fallback_chain": fallback_chain,
        "model_accepted": False,
        "port_local_model_available": trained,
        "port_local_model_trained": trained,
        "fallback_to_port_local_postprocess": False,
        "fallback_to_467441": bool(config.get("model_selection", {}).get("allow_fallback_to_467441", True)),
        "failed_reasons": failed_reasons or ["port_local_postprocess unavailable"],
    }


def _metrics_pass_acceptance(metrics: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    acceptance = config.get("model_selection", {}).get("port_local_model_acceptance", {})
    risk_eval = metrics.get("risk_level_evaluation", {})
    critical = risk_eval.get("critical_under_warning_count", 0)
    for target, thresholds in acceptance.items():
        if target == "rain_probability":
            if bool(thresholds.get("required", False)) and not metrics.get("rain_probability", {}).get("port_local_rain_model_trained", False):
                failures.append("rain_probability model required but not trained")
            continue
        target_metrics = metrics.get(target, {})
        h1 = target_metrics.get("H1", {})
        h2 = target_metrics.get("H2", {})
        max_h1 = thresholds.get("max_h1_mae_mps")
        max_h2 = thresholds.get("max_h2_mae_mps")
        if max_h1 is not None and _metric_value(h1, "MAE") is not None and _metric_value(h1, "MAE") > float(max_h1):
            failures.append(f"{target} H1 MAE above threshold")
        if max_h2 is not None and _metric_value(h2, "MAE") is not None and _metric_value(h2, "MAE") > float(max_h2):
            failures.append(f"{target} H2 MAE above threshold")
        if bool(thresholds.get("must_beat_persistence_h1", False)) and not bool(h1.get("beats_persistence", False)):
            failures.append(f"{target} H1 does not beat persistence")
        max_critical = int(thresholds.get("max_critical_under_warning_count", 0))
        if critical is not None and int(critical) > max_critical:
            failures.append(f"{target} critical_under_warning_count above threshold")
        if not h1 or not h2:
            failures.append(f"{target} H1/H2 metrics missing")
    return not failures, failures


def _metric_value(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if value is None:
        return None
    return float(value)


def select_dispatch_prediction_mode_v32(
    port_local_metrics: dict | None,
    postprocess_metrics: dict | None,
    nearby_cwa_metrics: dict | None,
    fallback_metrics: dict | None,
    dataset_readiness: dict,
    nearby_readiness: dict | None,
    config: dict,
) -> dict[str, Any]:
    chain = list(config.get("model_selection", {}).get("preferred_order", ["port_local_model", "port_local_postprocess", "nearby_cwa_historical_model", "fallback_baseline"]))
    base = select_dispatch_prediction_mode(port_local_metrics, postprocess_metrics, fallback_metrics, dataset_readiness, {**config, "model_selection": {**config.get("model_selection", {}), "preferred_order": chain}})
    nearby_available = bool((nearby_cwa_metrics or {}).get("nearby_cwa_historical_model_trained", False))
    nearby_accepted, nearby_failures = _nearby_metrics_pass_acceptance(nearby_cwa_metrics or {}, config) if nearby_available else (False, ["nearby_cwa_historical_model not trained"])
    nearby_ready = bool((nearby_readiness or {}).get("ready", False))
    if base["selected_mode"] == "port_local_postprocess" and bool(config.get("model_selection", {}).get("prefer_realtime_khwd_postprocess_over_nearby_historical", True)):
        base.update(
            {
                "fallback_chain": chain,
                "nearby_cwa_historical_model_available": nearby_available,
                "nearby_cwa_historical_model_accepted": nearby_accepted,
                "fallback_to_nearby_cwa_historical_model": False,
                "selection_reason": "KHWD realtime data is available, so port_local_postprocess is preferred over nearby CWA historical model.",
                "reason": "KHWD realtime data is available, so port_local_postprocess is preferred over nearby CWA historical model.",
            }
        )
        return base
    if base["selected_mode"] == "fallback_baseline" and nearby_ready and nearby_accepted:
        return {
            "selected_mode": "nearby_cwa_historical_model",
            "reason": "KHWD realtime unavailable; nearby CWA historical model accepted and all selected stations are closer than 467441.",
            "selection_reason": "KHWD realtime unavailable; nearby CWA historical model accepted and all selected stations are closer than 467441.",
            "fallback_chain": chain,
            "model_accepted": False,
            "nearby_cwa_historical_model_available": True,
            "nearby_cwa_historical_model_accepted": True,
            "fallback_to_port_local_postprocess": False,
            "fallback_to_nearby_cwa_historical_model": True,
            "fallback_to_467441": False,
            "failed_reasons": base.get("failed_reasons", []),
        }
    base.update(
        {
            "fallback_chain": chain,
            "nearby_cwa_historical_model_available": nearby_available,
            "nearby_cwa_historical_model_accepted": nearby_accepted,
            "fallback_to_nearby_cwa_historical_model": False,
            "failed_reasons": base.get("failed_reasons", []) + ([] if nearby_accepted else nearby_failures),
        }
    )
    return base


def _nearby_metrics_pass_acceptance(metrics: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    acceptance = config.get("nearby_cwa_historical_model_acceptance", {})
    risk = metrics.get("risk_level_evaluation", {})
    critical = risk.get("critical_under_warning_count", 0)
    for target in ["wind_speed", "wind_gust"]:
        thresholds = acceptance.get(target, {})
        values = metrics.get(target, {})
        h1 = values.get("H1", {})
        h2 = values.get("H2", {})
        if not h1 or not h2:
            failures.append(f"nearby {target} H1/H2 metrics missing")
            continue
        if h1.get("MAE") is not None and float(h1["MAE"]) > float(thresholds.get("max_h1_mae_mps", 999)):
            failures.append(f"nearby {target} H1 MAE above threshold")
        if h2.get("MAE") is not None and float(h2["MAE"]) > float(thresholds.get("max_h2_mae_mps", 999)):
            failures.append(f"nearby {target} H2 MAE above threshold")
        if bool(thresholds.get("must_beat_persistence_h1", False)) and not bool(h1.get("beats_persistence", False)):
            failures.append(f"nearby {target} H1 does not beat persistence")
        if critical is not None and int(critical) > int(thresholds.get("max_critical_under_warning_count", 0)):
            failures.append("nearby critical_under_warning_count above threshold")
    rain = metrics.get("rain_probability", {})
    if rain and acceptance.get("rain_probability"):
        h1 = rain.get("H1", {})
        if h1.get("Brier Score") is not None and float(h1["Brier Score"]) > float(acceptance["rain_probability"].get("max_brier_score", 999)):
            failures.append("nearby rain H1 Brier Score above threshold")
    return not failures, failures
