from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

try:
    from .config import ROOT, load_config
    from .evaluate import inverse_targets
    from .model import build_model, prediction_tensor
    from .preprocess import load_observations, prepare_station_frame
    from .data.fetch_qpesums import fetch_qpf_anchors, get_qpe_current_cached
    from .data.fetch_rain_spatial import build_station_list, fetch_nearby_precip_now, to_feature_vector
    from .data.fetch_cwa_forecast import get_pop_features
    from .cwa.location_resolver import load_or_resolve_cwa_location
    from .cwa.cwa_open_data_client import align_cwa_pop_to_anchors, load_cwa_api_key
    from .cwa.cwa_pop_quality import align_cwa_pop_quality_to_anchors
    from .cwa.location_resolver import resolve_cwa_forecast_source
    from .cwa.pop3h_client import fetch_pop3h
    from .forecast.rain_probability_blender import blend_with_cwa_pop3h
    from .postprocess.rain_probability_rules import apply_rain_probability_rules, assign_warning_levels
    from .postprocess.cwa_pop_prior import apply_cwa_pop_prior
    from .risk.confidence import reliability_profile
    from .risk.dispatch_risk_aggregator import aggregate_dispatch_risk, dispatch_suggestion
    from .risk.level_mapping import (
        map_rain_probability_to_level,
        map_wind_gust_to_level,
        map_wind_gust_to_operation_level,
        map_wind_speed_to_level,
        map_wind_speed_to_operation_level,
    )
    from .risk.risk_trigger_detail import build_risk_trigger_detail
    from .risk.action_mapping import map_dispatch_action_level
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from evaluate import inverse_targets
    from model import build_model, prediction_tensor
    from preprocess import load_observations, prepare_station_frame
    from data.fetch_qpesums import fetch_qpf_anchors, get_qpe_current_cached
    from data.fetch_rain_spatial import build_station_list, fetch_nearby_precip_now, to_feature_vector
    from data.fetch_cwa_forecast import get_pop_features
    from cwa.location_resolver import load_or_resolve_cwa_location
    from cwa.cwa_open_data_client import align_cwa_pop_to_anchors, load_cwa_api_key
    from cwa.cwa_pop_quality import align_cwa_pop_quality_to_anchors
    from cwa.location_resolver import resolve_cwa_forecast_source
    from cwa.pop3h_client import fetch_pop3h
    from forecast.rain_probability_blender import blend_with_cwa_pop3h
    from postprocess.rain_probability_rules import apply_rain_probability_rules, assign_warning_levels
    from postprocess.cwa_pop_prior import apply_cwa_pop_prior
    from risk.confidence import reliability_profile
    from risk.dispatch_risk_aggregator import aggregate_dispatch_risk, dispatch_suggestion
    from risk.level_mapping import (
        map_rain_probability_to_level,
        map_wind_gust_to_level,
        map_wind_gust_to_operation_level,
        map_wind_speed_to_level,
        map_wind_speed_to_operation_level,
    )
    from risk.risk_trigger_detail import build_risk_trigger_detail
    from risk.action_mapping import map_dispatch_action_level


UNITS = {
    "wind_speed": "m/s",
    "wind_gust": "m/s",
    "precipitation_1hr": "mm",
    "tide_level": "cm",
    "visibility": "m",
}
TAIPEI = timezone(timedelta(hours=8))


def _latest_grades(project: Path, station_id: str, target_group: str, target_columns: list[str]) -> dict[str, str]:
    path = project / "results" / "evaluation" / f"{station_id}_{target_group}_metrics.json"
    if not path.exists():
        return {f"H{i}": "acceptable" for i in range(1, 5)}
    report = json.loads(path.read_text(encoding="utf-8"))
    if len(target_columns) == 1:
        return report.get("accuracy_grade", {}).get(target_columns[0], {})
    merged: dict[str, str] = {}
    for label in ["H1", "H2", "H3", "H4"]:
        grades = [report.get("accuracy_grade", {}).get(col, {}).get(label, "acceptable") for col in target_columns]
        merged[label] = "poor" if "poor" in grades else "acceptable" if "acceptable" in grades else "excellent"
    return merged


def predict(
    station_id: str,
    target_group: str,
    recent_observations: pd.DataFrame,
    config_path: str = "config.yaml",
    return_uncertainty: bool = False,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    if target_group == "precipitation" and bool(cfg.get("rain_postprocess", {}).get("enabled", False)):
        return predict_rain_probability_v23(station_id, recent_observations, None, config_path, project_root)
    data_sources: dict[str, Any] = {}
    if target_group == "precipitation":
        qpf = _try_qpesums_qpf(cfg)
        if qpf:
            return _qpf_prediction(station_id, qpf, cfg)
        recent_observations, data_sources = _attach_precipitation_features(recent_observations, cfg, project)
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_{target_group}_best.pt"
    scaler_path = project / "scalers" / f"{station_id}_{target_group}_scaler.pkl"
    if not ckpt_path.exists():
        raise FileNotFoundError(ckpt_path)
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    scaler_bundle = joblib.load(scaler_path)
    model_type = checkpoint["model_type"]
    target_columns = list(checkpoint["target_columns"])
    frame, invalid, _ = prepare_station_frame(recent_observations, cfg, station_id, target_columns)
    features = list(checkpoint["feature_columns"])
    lookback = int(float(cfg["lookback_hours"]) * 60 / int(cfg["time_step_minutes"]))
    recent = frame[features].tail(lookback)
    if len(recent) < lookback:
        raise ValueError(f"Need at least {lookback} recent rows after resampling")
    if invalid.tail(lookback).any():
        raise ValueError("Recent observations contain invalid gaps inside lookback window")

    scaler = scaler_bundle["scaler"]
    X = scaler.transform(recent.astype(float))
    model = build_model(model_type, int(checkpoint["n_features"]), checkpoint["config"].get("model", {}))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    x = torch.as_tensor(X[None, :, :], dtype=torch.float32)

    rain_probability = None
    if model_type == "twostage_lstm":
        with torch.no_grad():
            raw = model(x)
        rain_probability = raw["probability"].cpu().numpy()
        pred = raw["amount"].cpu().numpy()
        pred = np.where(rain_probability > float(checkpoint["config"]["targets"]["precipitation"].get("inference_cls_threshold", 0.5)), pred, 0.0)
        if pred.ndim == 2:
            pred = pred[..., None]
        std = None
    elif return_uncertainty:
        model.train()
        preds = []
        with torch.no_grad():
            for _ in range(50):
                p = prediction_tensor(model, x, model_type).cpu().numpy()
                if p.ndim == 2:
                    p = p[..., None]
                preds.append(p)
        arr = np.concatenate(preds, axis=0)
        pred = arr.mean(axis=0, keepdims=True)
        std = inverse_targets(arr, scaler_bundle, target_columns).std(axis=0)
    else:
        with torch.no_grad():
            pred = prediction_tensor(model, x, model_type).cpu().numpy()
        if pred.ndim == 2:
            pred = pred[..., None]
        std = None

    pred_orig = inverse_targets(pred, scaler_bundle, target_columns)[0]
    last_time = pd.to_datetime(recent.index[-1]).to_pydatetime()
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=TAIPEI)
    grades = _latest_grades(project, station_id, target_group, target_columns)
    anchors = []
    for idx, offset in enumerate(cfg["anchor_offsets_minutes"]):
        item: dict[str, Any] = {
            "label": f"H{idx + 1}",
            "offset_minutes": int(offset),
            "timestamp": (last_time + timedelta(minutes=int(offset))).isoformat(),
        }
        for col_idx, col in enumerate(target_columns):
            value = {"value": round(float(pred_orig[idx, col_idx]), 3), "unit": UNITS.get(col)}
            if return_uncertainty and std is not None:
                value["std"] = round(float(std[idx, col_idx]), 3)
            item[col] = value
            if col == "precipitation_1hr" and rain_probability is not None:
                rain_prob = float(rain_probability[0, idx])
                heavy_threshold = float(checkpoint["config"]["targets"]["precipitation"].get("rain_threshold_heavy", 10.0))
                item["rain_probability"] = round(rain_prob, 4)
                item["heavy_rain_prob"] = round(rain_prob if float(pred_orig[idx, col_idx]) > heavy_threshold else 0.0, 4)
                item["data_source"] = _precipitation_data_source(data_sources)
                item["spatial_available"] = bool(data_sources.get("spatial_rain", {}).get("available", False))
                item["cwa_available"] = bool(data_sources.get("cwa_forecast", {}).get("available", False))
        anchors.append(item)
    return {
        "station_id": station_id,
        "target_group": target_group,
        "anchors": anchors,
        "accuracy_grade": grades,
        "model_version": checkpoint.get("model_version", "baseline_lstm_v1"),
        **({"data_sources": data_sources} if target_group == "precipitation" else {}),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
    }


def _qpesums_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("qpesums", {}).get("enabled", False))


def _try_qpesums_qpf(cfg: dict[str, Any]) -> dict[str, float] | None:
    if not _qpesums_enabled(cfg):
        return None
    try:
        return fetch_qpf_anchors(dataid=cfg.get("qpesums", {}).get("qpf_dataid"))
    except Exception:
        return None


def _attach_qpesums_qpe(recent_observations: pd.DataFrame, cfg: dict[str, Any], project: Path) -> pd.DataFrame:
    if not _qpesums_enabled(cfg):
        return recent_observations
    try:
        qpe = get_qpe_current_cached(project, int(cfg.get("qpesums", {}).get("cache_ttl_seconds", 600)))
    except Exception:
        return recent_observations
    out = recent_observations.copy()
    out["qpe_1hr_mm"] = float(qpe.get("qpe_1hr_mm", 0.0) or 0.0)
    out["qpe_3hr_mm"] = float(qpe.get("qpe_3hr_mm", 0.0) or 0.0)
    return out


def _attach_precipitation_features(recent_observations: pd.DataFrame, cfg: dict[str, Any], project: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = _attach_qpesums_qpe(recent_observations, cfg, project)
    data_sources: dict[str, Any] = {}
    feature_cfg = cfg.get("features", {})
    extra: dict[str, float] = {}

    spatial_cfg = feature_cfg.get("spatial_rain", {})
    if bool(spatial_cfg.get("enabled", False)):
        try:
            spatial = fetch_nearby_precip_now(project)
            spatial_feats = to_feature_vector(spatial, int(spatial_cfg.get("top_n", 3)))
            extra.update(spatial_feats)
            data_sources["spatial_rain"] = {
                "available": bool(spatial_feats.get("nearby_available", 0.0)),
                "stations": build_station_list(project),
                "obs_time": spatial.get("obs_time"),
            }
        except Exception:
            extra.update({"nearby_precip_1": 0.0, "nearby_precip_2": 0.0, "nearby_precip_3": 0.0, "nearby_available": 0.0})
            data_sources["spatial_rain"] = {"available": False, "stations": [], "obs_time": None}

    cwa_cfg = feature_cfg.get("cwa_forecast", {})
    if bool(cwa_cfg.get("enabled", False)):
        cwa_feats = get_pop_features(
            location=str(cwa_cfg.get("location_name", "鼓山區")),
            project_root=project,
            cache_ttl=int(cwa_cfg.get("cache_ttl_sec", 3600)),
        )
        extra.update(cwa_feats)
        data_sources["cwa_forecast"] = {
            "available": bool(cwa_feats.get("cwa_available", 0.0)),
            "pop_current": cwa_feats.get("cwa_pop_current", 0.0),
            "pop_next": cwa_feats.get("cwa_pop_next", 0.0),
            "data_age_hr": round(float(cwa_feats.get("cwa_data_age_hr", 1.0)) * 6, 3),
        }

    if extra:
        out = out.copy()
        for col, value in extra.items():
            if col not in out.columns:
                out[col] = 0.0
            out.loc[out.index[-1], col] = value
    return out, data_sources


def _precipitation_data_source(data_sources: dict[str, Any]) -> str:
    active = [name for name, info in data_sources.items() if bool(info.get("available", False))]
    return "lstm_only" if not active else "+".join([*active, "lstm"])


def _qpf_prediction(station_id: str, qpf: dict[str, float], cfg: dict[str, Any]) -> dict[str, Any]:
    anchors = []
    now = datetime.now(TAIPEI)
    for idx, offset in enumerate(cfg["anchor_offsets_minutes"]):
        anchors.append(
            {
                "label": f"H{idx + 1}",
                "offset_minutes": int(offset),
                "timestamp": (now + timedelta(minutes=int(offset))).isoformat(),
                "precipitation_1hr": {"value": round(float(qpf.get(f"qpf_{int(offset)}min_mm", 0.0)), 3), "unit": "mm"},
                "rain_probability": None,
                "heavy_rain_prob": None,
                "data_source": "qpesums_qpf",
            }
        )
    return {
        "station_id": station_id,
        "target_group": "precipitation",
        "anchors": anchors,
        "accuracy_grade": {f"H{i}": "acceptable" for i in range(1, 5)},
        "model_version": "baseline_lstm_v2.2",
        "data_sources": {"qpesums_qpf": {"available": True}},
        "generated_at": now.isoformat(timespec="seconds"),
    }


def predict_from_file(
    station_id: str,
    target_group: str,
    data_path: str | Path,
    config_path: str = "config.yaml",
    return_uncertainty: bool = False,
) -> dict[str, Any]:
    return predict(station_id, target_group, load_observations(data_path), config_path, return_uncertainty)


def predict_dispatch_risk_v24(
    target_station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    cwa_pop: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    rain = predict_rain_probability_v23(target_station_id, recent_observations, nearby_observations, config_path, project)
    cwa_prior_input = cwa_pop if cwa_pop is not None else rain.get("cwa", {})
    rain_probs = {item["label"]: float(item["rain_probability"]) for item in rain["anchors"]}
    prior = apply_cwa_pop_prior(rain_probs, cwa_prior_input, cfg)
    rain_probs = {label: float(value) for label, value in prior["final_probabilities"].items()}
    rain_levels = {label: map_rain_probability_to_level(prob, cfg) for label, prob in rain_probs.items()}

    wind = predict(target_station_id, "wind_speed_gust", recent_observations, config_path, False, project)
    wind_speed_values: dict[str, float] = {}
    wind_gust_values: dict[str, float] = {}
    for item in wind["anchors"]:
        label = str(item["label"])
        wind_speed_values[label] = max(0.0, float(item.get("wind_speed", {}).get("value", 0.0)))
        wind_gust_values[label] = max(0.0, float(item.get("wind_gust", {}).get("value", 0.0)))
    wind_levels = {label: map_wind_speed_to_level(value, cfg) for label, value in wind_speed_values.items()}
    gust_levels = {label: map_wind_gust_to_level(value, cfg, use_buffer=True) for label, value in wind_gust_values.items()}
    dispatch_levels = aggregate_dispatch_risk(rain_levels, wind_levels, gust_levels, None, None, cfg)
    reliability = reliability_profile(cfg)

    wind_by_label = {item["label"]: item for item in wind["anchors"]}
    rain_by_label = {item["label"]: item for item in rain["anchors"]}
    forecast_anchors = []
    for label, offset in _forecast_anchor_items(cfg):
        wind_item = wind_by_label.get(label, {})
        rain_item = rain_by_label.get(label, {})
        risk_level = dispatch_levels.get(label, "normal")
        forecast_anchors.append(
            {
                "label": label,
                "offset_minutes": int(offset),
                "timestamp": wind_item.get("timestamp") or rain_item.get("timestamp"),
                "rain": {
                    "probability": round(float(rain_probs.get(label, 0.0)), 4),
                    "level": rain_levels.get(label, "normal"),
                    "source": "model_postprocess_prior" if prior["trace"].get("cwa_pop_used_as_postprocess_prior") else "model_postprocess",
                    "confidence": reliability.get("rain_probability", "low_to_medium"),
                },
                "wind_speed": {
                    "predicted_mps": round(float(wind_speed_values.get(label, 0.0)), 3),
                    "level": wind_levels.get(label, "normal"),
                    "confidence": reliability.get("wind_speed", "high"),
                },
                "wind_gust": {
                    "predicted_mps": round(float(wind_gust_values.get(label, 0.0)), 3),
                    "level": gust_levels.get(label, "normal"),
                    "confidence": reliability.get("wind_gust", "medium_high"),
                    "buffer_applied": True,
                    "buffer_mps": float(cfg.get("wind_gust", {}).get("uncertainty_buffer_mps", 1.2)),
                },
                "visibility": {
                    "available": visibility_observations is not None and not visibility_observations.empty,
                    "level": None,
                    "confidence": "unavailable" if visibility_observations is None or visibility_observations.empty else reliability.get("visibility", "optional"),
                },
                "tide": {
                    "available": tide_observations is not None and not tide_observations.empty,
                    "level": None,
                    "confidence": reliability.get("tide", "reference_only"),
                },
                "dispatch_risk_level": risk_level,
                "dispatch_suggestion": dispatch_suggestion(risk_level),
            }
        )

    nearby_precip = rain.get("nearby_precip", {})
    nearby_count = int(nearby_precip.get("station_count", nearby_precip.get("active_station_count", 0)) or 0)
    scope = cfg.get("spatial_scope", {})
    return {
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.4"),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "target_area": {
            "name": scope.get("target_area_name", "Kaohsiung Port"),
            "port_code": scope.get("port_code", "KHH"),
            "target_station_id": str(target_station_id),
        },
        "forecast_anchors": forecast_anchors,
        "data_availability": {
            "target_station_available": recent_observations is not None and not recent_observations.empty,
            "nearby_station_available": bool(rain.get("nearby_precip", {}).get("available", False)),
            "nearby_station_count": nearby_count,
            "cwa_pop_available": bool(cwa_prior_input.get("available", False)) if isinstance(cwa_prior_input, dict) else False,
            "tide_available": tide_observations is not None and not tide_observations.empty,
            "visibility_available": visibility_observations is not None and not visibility_observations.empty,
        },
        "reliability": reliability,
        "trace": {
            "port_local_scope": scope.get("mode", "port_local") == "port_local",
            "multi_station_input": nearby_observations is not None or bool(rain.get("nearby_precip", {}).get("available", False)),
            "city_wide_forecast_as_target": False,
            "train_inference_mismatch_prevented": True,
            "cwa_pop_used_as_model_input": False,
            "cwa_pop_used_as_postprocess_prior": bool(prior["trace"].get("cwa_pop_used_as_postprocess_prior", False)),
            "dispatch_risk_aggregation": "max_level_rule",
            "base_models": {
                "rain": rain.get("base_model_version", rain.get("model_version")),
                "wind_speed_gust": wind.get("model_version"),
            },
        },
    }


def predict_dispatch_risk_v25(
    target_station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    checkpoint, _, _, recent, raw_prob, _ = _run_raw_precipitation_lstm(target_station_id, recent_observations, cfg, project)
    raw_probs = {f"H{i + 1}": float(raw_prob[0, i]) for i in range(raw_prob.shape[1])}
    nearby = _summarize_nearby_precipitation(nearby_observations, project)
    nearby_rule = apply_rain_probability_rules(raw_probs, nearby, {"available": False}, cfg)
    nearby_probs = {label: float(value) for label, value in nearby_rule["adjusted_probs"].items()}

    generated_at = datetime.now(TAIPEI)
    cwa = cwa_forecast if cwa_forecast is not None else _fetch_cwa_forecast_v25(cfg, project, generated_at)
    prior = apply_cwa_pop_prior(nearby_probs, cwa, cfg)
    final_rain_probs = {label: float(value) for label, value in prior["final_probabilities"].items()}
    rain_levels = {label: map_rain_probability_to_level(prob, cfg) for label, prob in final_rain_probs.items()}

    wind = predict(target_station_id, "wind_speed_gust", recent_observations, config_path, False, project)
    wind_speed_values: dict[str, float] = {}
    wind_gust_values: dict[str, float] = {}
    for item in wind["anchors"]:
        label = str(item["label"])
        wind_speed_values[label] = max(0.0, float(item.get("wind_speed", {}).get("value", 0.0)))
        wind_gust_values[label] = max(0.0, float(item.get("wind_gust", {}).get("value", 0.0)))

    wind_operation = {label: map_wind_speed_to_operation_level(value, cfg) for label, value in wind_speed_values.items()}
    gust_operation = {label: map_wind_gust_to_operation_level(value, cfg, use_buffer=True) for label, value in wind_gust_values.items()}
    wind_levels = {label: detail["operation_level"] for label, detail in wind_operation.items()}
    gust_levels = {label: detail["operation_level"] for label, detail in gust_operation.items()}
    dispatch_levels = aggregate_dispatch_risk(rain_levels, wind_levels, gust_levels, None, None, cfg)
    reliability = reliability_profile(cfg)
    trigger_priority = cfg.get("risk_trigger", {}).get("trigger_priority", ["wind_gust", "wind_speed", "rain_probability", "visibility", "tide"])

    wind_by_label = {item["label"]: item for item in wind["anchors"]}
    forecast_anchors = []
    for label, offset in _forecast_anchor_items(cfg):
        wind_item = wind_by_label.get(label, {})
        risk_level = dispatch_levels.get(label, "normal")
        source_detail = prior.get("source_detail", {}).get(label, {})
        anchor_quality = cwa.get("anchor_pop_quality", {}).get(label) if isinstance(cwa.get("anchor_pop_quality", {}), dict) else None
        nearby_postprocess_applied = bool(nearby_probs.get(label, raw_probs.get(label, 0.0)) != raw_probs.get(label, 0.0))
        source_detail = {
            "model_used": True,
            "nearby_postprocess_applied": nearby_postprocess_applied,
            "cwa_prior_applied": bool(source_detail.get("cwa_prior_applied", False)),
            "cwa_weight": float(source_detail.get("cwa_weight", 0.0)),
            "cwa_dataset_id": source_detail.get("cwa_dataset_id", cwa.get("dataset_id")),
            "cwa_location_name": source_detail.get("cwa_location_name", cwa.get("location_name")),
            "cwa_element_name": source_detail.get("cwa_element_name", cwa.get("element_name")),
            "cwa_source_resolution": source_detail.get("cwa_source_resolution", cwa.get("source_resolution")),
            "cwa_pop_quality": source_detail.get("cwa_pop_quality") or anchor_quality,
        }
        trigger_detail = build_risk_trigger_detail(
            risk_level,
            rain_levels.get(label, "normal"),
            wind_levels.get(label, "normal"),
            gust_levels.get(label, "normal"),
            None,
            None,
            {
                "rain_probability": reliability.get("rain_probability", "low_to_medium"),
                "wind_speed": reliability.get("wind_speed", "high"),
                "wind_gust": reliability.get("wind_gust", "medium_high"),
                "visibility": "unavailable",
                "tide": reliability.get("tide", "reference_only"),
            },
            trigger_priority,
        )
        action = map_dispatch_action_level(risk_level, str(trigger_detail["primary_trigger_reliability"]))
        forecast_anchors.append(
            {
                "label": label,
                "offset_minutes": int(offset),
                "timestamp": wind_item.get("timestamp"),
                "rain": {
                    "raw_model_probability": round(float(raw_probs.get(label, 0.0)), 4),
                    "nearby_adjusted_probability": round(float(nearby_probs.get(label, raw_probs.get(label, 0.0))), 4),
                    "cwa_adjusted_probability": (
                        round(float(final_rain_probs[label]), 4) if source_detail["cwa_prior_applied"] else None
                    ),
                    "final_probability": round(float(final_rain_probs.get(label, 0.0)), 4),
                    "level": rain_levels.get(label, "normal"),
                    "confidence": reliability.get("rain_probability", "low_to_medium"),
                    "source_detail": source_detail,
                },
                "wind_speed": {
                    "predicted_mps": round(float(wind_speed_values.get(label, 0.0)), 3),
                    "beaufort": wind_operation[label]["beaufort"],
                    "operation_level": wind_operation[label]["operation_level"],
                    "operation_label": wind_operation[label]["operation_label"],
                    "confidence": reliability.get("wind_speed", "high"),
                },
                "wind_gust": {
                    "predicted_mps": round(float(wind_gust_values.get(label, 0.0)), 3),
                    "beaufort": gust_operation[label]["beaufort"],
                    "operation_level": gust_operation[label]["operation_level"],
                    "operation_label": gust_operation[label]["operation_label"],
                    "confidence": reliability.get("wind_gust", "medium_high"),
                    "buffer_applied": gust_operation[label]["buffer_applied"],
                    "buffer_mps": gust_operation[label]["buffer_mps"],
                    "original_level_without_buffer": gust_operation[label]["original_level_without_buffer"],
                },
                "visibility": {
                    "available": visibility_observations is not None and not visibility_observations.empty,
                    "level": None,
                    "confidence": "unavailable" if visibility_observations is None or visibility_observations.empty else reliability.get("visibility", "optional"),
                },
                "tide": {
                    "available": tide_observations is not None and not tide_observations.empty,
                    "level": None,
                    "confidence": reliability.get("tide", "reference_only"),
                },
                "dispatch_risk_level": risk_level,
                "risk_trigger_detail": trigger_detail,
                "dispatch_action_level": action["dispatch_action_level"],
                "dispatch_action": action,
                "dispatch_suggestion": action["action_description"],
            }
        )

    nearby_count = len(nearby.get("station_values_1hr", {}) or {})
    scope = cfg.get("spatial_scope", {})
    return {
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.5"),
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "target_area": {
            "name": scope.get("target_area_name", "Kaohsiung Port"),
            "port_code": scope.get("port_code", "KHH"),
            "target_station_id": str(target_station_id),
        },
        "forecast_anchors": forecast_anchors,
        "cwa_forecast": _public_cwa_forecast(cwa),
        "data_availability": {
            "target_station_available": recent_observations is not None and not recent_observations.empty,
            "nearby_station_available": bool(nearby.get("available", False)),
            "nearby_station_count": nearby_count,
            "cwa_pop_available": bool(cwa.get("available", False)) if isinstance(cwa, dict) else False,
            "tide_available": tide_observations is not None and not tide_observations.empty,
            "visibility_available": visibility_observations is not None and not visibility_observations.empty,
        },
        "reliability": reliability,
        "trace": {
            "port_local_scope": scope.get("mode", "port_local") == "port_local",
            "multi_station_input": nearby_observations is not None or bool(nearby.get("available", False)),
            "city_wide_forecast_as_target": False,
            "train_inference_mismatch_prevented": True,
            "cwa_pop_used_as_model_input": False,
            "cwa_pop_used_as_postprocess_prior": bool(prior["trace"].get("cwa_pop_used_as_postprocess_prior", False)),
            "cwa_pop_quality_gate_enabled": bool(cfg.get("cwa_pop_quality", {}).get("enabled", False)),
            "zero_pop_distinguished_from_missing": bool(cfg.get("cwa_pop_quality", {}).get("distinguish_zero_and_missing", False)),
            "normal_state_primary_trigger_none": bool(cfg.get("risk_trigger", {}).get("use_none_trigger_when_normal", True)),
            "risk_trigger_semantics_patch_applied": True,
            "dispatch_risk_aggregation": "max_level_rule",
            "base_models": {
                "rain": checkpoint.get("model_version", "unknown"),
                "wind_speed_gust": wind.get("model_version"),
            },
        },
    }


def _fetch_cwa_forecast_v25(cfg: dict[str, Any], project: Path, generated_at: datetime) -> dict[str, Any]:
    cwa_cfg = cfg.get("cwa_open_data", {})
    if not cwa_cfg.get("enabled", False):
        return {"available": False, "reason": "cwa_open_data disabled", "anchor_pop": {}}
    api_key = load_cwa_api_key(str(cwa_cfg.get("api_key_env", "CWA_API_KEY")), project)
    resolved_path = project / "config" / "resolved_cwa_forecast_source.json"
    resolved: dict[str, Any]
    if resolved_path.exists():
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    else:
        resolved = resolve_cwa_forecast_source(
            cwa_cfg.get("pop_datasets", {}).get("candidates", []),
            [str(item) for item in cwa_cfg.get("location_candidates", [])],
            cwa_cfg.get("element_name_candidates", {}),
            api_key,
            cfg,
            project,
        )
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    if not resolved.get("available", False):
        return {**resolved, "anchor_pop": {}}
    anchors = {label: offset for label, offset in _forecast_anchor_items(cfg)}
    anchor_pop = align_cwa_pop_to_anchors(resolved.get("valid_times", []), generated_at, anchors)
    anchor_quality = align_cwa_pop_quality_to_anchors(resolved.get("valid_times", []), generated_at, anchors, resolved)
    return {
        **resolved,
        "anchor_pop": anchor_pop,
        "anchor_pop_quality": anchor_quality,
        "raw_unit": "%",
        "normalized_unit": "probability_0_1",
    }


def _public_cwa_forecast(cwa: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(cwa.get("available", False)),
        "dataset_id": cwa.get("dataset_id"),
        "location_name": cwa.get("location_name"),
        "element_name": cwa.get("element_name"),
        "source_resolution": cwa.get("source_resolution"),
        "fetched_at": cwa.get("fetched_at"),
        "anchor_pop": cwa.get("anchor_pop", {}),
        "anchor_pop_quality": cwa.get("anchor_pop_quality", {}),
        "reason": cwa.get("reason"),
    }


def predict_dispatch_risk_v251(
    target_station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    return predict_dispatch_risk_v25(
        target_station_id,
        recent_observations,
        nearby_observations,
        cwa_forecast,
        tide_observations,
        visibility_observations,
        config_path,
        project_root,
    )


def predict_dispatch_risk_v252(
    target_station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    return predict_dispatch_risk_v25(
        target_station_id,
        recent_observations,
        nearby_observations,
        cwa_forecast,
        tide_observations,
        visibility_observations,
        config_path,
        project_root,
    )


def _forecast_anchor_items(cfg: dict[str, Any]) -> list[tuple[str, int]]:
    forecast = cfg.get("forecast", {}).get("anchors", {})
    if forecast:
        return [(str(label), int(offset)) for label, offset in forecast.items()]
    return [(f"H{idx + 1}", int(offset)) for idx, offset in enumerate(cfg.get("anchor_offsets_minutes", [30, 60, 90, 120]))]


def predict_rain_probability_v23(
    station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    checkpoint, scaler_bundle, frame, recent, raw_prob, amount_orig = _run_raw_precipitation_lstm(
        station_id, recent_observations, cfg, project
    )
    raw_probs = {f"H{i + 1}": float(raw_prob[0, i]) for i in range(raw_prob.shape[1])}
    nearby = _summarize_nearby_precipitation(nearby_observations, project)
    cwa = _fetch_resolved_cwa_pop(cfg, project)
    rule_result = apply_rain_probability_rules(raw_probs, nearby, cwa, cfg)
    blend_result = blend_with_cwa_pop3h(rule_result["adjusted_probs"], cwa, cfg)
    final_probs = blend_result["final_probs"]
    warning_levels = assign_warning_levels(final_probs, cfg)

    last_time = pd.to_datetime(recent.index[-1]).to_pydatetime()
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=TAIPEI)
    threshold = float(cfg["targets"]["precipitation"].get("inference_cls_threshold", 0.5))
    anchors = []
    for idx, offset in enumerate(cfg["anchor_offsets_minutes"]):
        label = f"H{idx + 1}"
        final_prob = float(final_probs[label])
        anchors.append(
            {
                "label": label,
                "offset_minutes": int(offset),
                "timestamp": (last_time + timedelta(minutes=int(offset))).isoformat(),
                "raw_lstm_probability": round(raw_probs[label], 4),
                "rule_adjusted_probability": round(float(rule_result["adjusted_probs"][label]), 4),
                "final_probability": round(final_prob, 4),
                "rain_probability": round(final_prob, 4),
                "precipitation_1hr": {
                    "value": round(float(amount_orig[idx]) if final_prob > threshold else 0.0, 3),
                    "unit": "mm",
                },
                "heavy_rain_prob": round(final_prob if float(amount_orig[idx]) > cfg["targets"]["precipitation"].get("rain_threshold_heavy", 10.0) else 0.0, 4),
                "warning_level": warning_levels[label],
                "cwa_blending_applied": bool(blend_result.get("cwa_blending_applied", False) and label in {"H3", "H4"}),
                "applied_rules": [rule["rule_id"] for rule in rule_result["applied_rules"] if label in rule.get("affected_anchors", [])],
            }
        )
    return {
        "station_id": station_id,
        "target_group": "precipitation",
        "model_version": "rain_lstm_postprocess_v2.3",
        "base_model_version": checkpoint.get("model_version", "unknown"),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "lookback_hours": cfg.get("rain_postprocess", {}).get("lookback_hours", cfg.get("lookback_hours")),
        "anchors": anchors,
        "cwa": cwa,
        "nearby_precip": {
            "available": nearby.get("available", False),
            "station_count": len(nearby.get("station_values_1hr", {}) or {}),
            "max_1hr": nearby.get("max_1hr", 0.0),
            "mean_1hr": nearby.get("mean_1hr", 0.0),
            "active_station_count": nearby.get("active_station_count", 0),
        },
        "trace": {
            "train_inference_mismatch_fixed": True,
            "pure_temporal_lstm": True,
            "postprocess_enabled": True,
            "cwa_blending_enabled": bool(cfg.get("rain_postprocess", {}).get("blending", {}).get("enabled", True)),
        },
    }


def _run_raw_precipitation_lstm(station_id: str, observations: pd.DataFrame, cfg: dict[str, Any], project: Path):
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_precipitation_best.pt"
    scaler_path = project / "scalers" / f"{station_id}_precipitation_scaler.pkl"
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    scaler_bundle = joblib.load(scaler_path)
    target_columns = list(checkpoint["target_columns"])
    frame, invalid, _ = prepare_station_frame(observations, cfg, station_id, target_columns)
    features = list(checkpoint["feature_columns"])
    forbidden = [col for col in features if col.startswith("nearby_") or col.startswith("cwa_") or col.startswith("qpe_")]
    if forbidden:
        raise ValueError(f"Pure temporal rainfall LSTM contains forbidden inference-only features: {forbidden}")
    lookback = int(float(cfg.get("rain_postprocess", {}).get("lookback_hours", cfg["lookback_hours"])) * 60 / int(cfg["time_step_minutes"]))
    recent = frame[features].tail(lookback)
    if len(recent) < lookback:
        raise ValueError(f"Need at least {lookback} recent rows after resampling")
    if invalid.tail(lookback).any():
        raise ValueError("Recent observations contain invalid gaps inside lookback window")
    X = scaler_bundle["scaler"].transform(recent.astype(float))
    model = build_model(checkpoint["model_type"], int(checkpoint["n_features"]), checkpoint["config"].get("model", {}))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    with torch.no_grad():
        raw = model(torch.as_tensor(X[None, :, :], dtype=torch.float32))
    probability = raw["probability"].cpu().numpy()
    amount_scaled = raw["amount"].cpu().numpy()
    amount_orig = inverse_targets(amount_scaled[..., None], scaler_bundle, target_columns)[0, :, 0]
    return checkpoint, scaler_bundle, frame, recent, probability, amount_orig


def _summarize_nearby_precipitation(nearby_observations: pd.DataFrame | None, project: Path) -> dict[str, Any]:
    if nearby_observations is not None and not nearby_observations.empty:
        values = nearby_observations.get("precip_1hr", pd.Series(dtype=float)).astype(float)
        station_values = {
            str(row.get("station_id", idx)): float(row.get("precip_1hr", 0.0) or 0.0)
            for idx, row in nearby_observations.iterrows()
        }
        return {
            "station_values_1hr": station_values,
            "max_1hr": float(values.max()) if len(values) else 0.0,
            "mean_1hr": float(values.mean()) if len(values) else 0.0,
            "active_station_count": int((values > 0).sum()) if len(values) else 0,
            "available": True,
        }
    result = fetch_nearby_precip_now(project)
    values = [float(item.get("precip_1hr", 0.0) or 0.0) for item in result.get("nearby", [])]
    return {
        "station_values_1hr": {str(item.get("station_id")): float(item.get("precip_1hr", 0.0) or 0.0) for item in result.get("nearby", [])},
        "max_1hr": max(values) if values else 0.0,
        "mean_1hr": float(np.mean(values)) if values else 0.0,
        "active_station_count": int(sum(value > 0 for value in values)),
        "available": bool(result.get("available", False)),
        "obs_time": result.get("obs_time"),
    }


def _fetch_resolved_cwa_pop(cfg: dict[str, Any], project: Path) -> dict[str, Any]:
    cwa_cfg = cfg.get("rain_postprocess", {}).get("cwa_pop3h", {})
    if not cwa_cfg.get("enabled", False):
        return {"available": False, "location_name": None, "current": None, "next": None, "records": [], "fetched_at": None}
    resolved = load_or_resolve_cwa_location(cfg, project)
    location = resolved.get("resolved_location_name", cwa_cfg.get("fallback_location", "前鎮區"))
    return fetch_pop3h(str(location), cache_minutes=int(cwa_cfg.get("cache_minutes", 30)), project_root=project)
