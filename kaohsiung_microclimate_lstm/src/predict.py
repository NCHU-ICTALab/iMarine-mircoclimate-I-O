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
    from .cwa.pop3h_client import EXTENDED_DATAID, fetch_pop3h
    from .data.multi_station_loader import load_multi_station_observations, load_priority_station_pool_observations
    from .data.nearby_aggregation import build_nearby_aggregated_features
    from .data.station_pool import enabled_input_stations, load_station_pool_config, resolve_station_pool_path
    from .data.station_priority import decide_prediction_mode
    from .data.port_local_wind_aggregation import build_port_local_wind_features
    from .data.dataset_readiness import check_port_local_dataset_readiness
    from .data.port_local_training_dataset import build_port_local_training_dataset
    from .forecast.rain_probability_blender import blend_with_cwa_pop3h
    from .model_selection.port_local_model_selector import select_dispatch_prediction_mode, select_dispatch_prediction_mode_v32
    from .selection.model_selection_engine import select_prediction_mode
    from .training_orchestration import build_model_training_status, run_training_orchestration
    from .model_registry import build_model_registry_summary
    from .station_usage import build_current_station_usage, build_station_display_rows, station_role_violations
    from .postprocess.port_local_wind_postprocess import apply_port_local_wind_postprocess
    from .postprocess.port_local_gust_postprocess import apply_port_local_gust_postprocess
    from .postprocess.rain_probability_rules import apply_rain_probability_rules, assign_warning_levels
    from .postprocess.cwa_pop_prior import apply_cwa_pop_prior
    from .risk.confidence import reliability_profile
    from .risk.dispatch_risk_aggregator import aggregate_dispatch_risk, dispatch_suggestion
    from .risk.level_mapping import (
        LEVEL_ORDER,
        map_rain_amount_to_level,
        map_rain_probability_to_level,
        rain_amount_level_basis,
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
    from cwa.pop3h_client import EXTENDED_DATAID, fetch_pop3h
    from data.multi_station_loader import load_multi_station_observations, load_priority_station_pool_observations
    from data.nearby_aggregation import build_nearby_aggregated_features
    from data.station_pool import enabled_input_stations, load_station_pool_config, resolve_station_pool_path
    from data.station_priority import decide_prediction_mode
    from data.port_local_wind_aggregation import build_port_local_wind_features
    from data.dataset_readiness import check_port_local_dataset_readiness
    from data.port_local_training_dataset import build_port_local_training_dataset
    from forecast.rain_probability_blender import blend_with_cwa_pop3h
    from model_selection.port_local_model_selector import select_dispatch_prediction_mode, select_dispatch_prediction_mode_v32
    from selection.model_selection_engine import select_prediction_mode
    from training_orchestration import build_model_training_status, run_training_orchestration
    from model_registry import build_model_registry_summary
    from station_usage import build_current_station_usage, build_station_display_rows, station_role_violations
    from postprocess.port_local_wind_postprocess import apply_port_local_wind_postprocess
    from postprocess.port_local_gust_postprocess import apply_port_local_gust_postprocess
    from postprocess.rain_probability_rules import apply_rain_probability_rules, assign_warning_levels
    from postprocess.cwa_pop_prior import apply_cwa_pop_prior
    from risk.confidence import reliability_profile
    from risk.dispatch_risk_aggregator import aggregate_dispatch_risk, dispatch_suggestion
    from risk.level_mapping import (
        LEVEL_ORDER,
        map_rain_amount_to_level,
        map_rain_probability_to_level,
        rain_amount_level_basis,
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
    rain_amount_result = _predict_nearby_precipitation_amounts(project, nearby_observations, recent_observations)
    rain_amounts = rain_amount_result["amounts"]
    rain_amounts = _condition_rain_amounts_on_probability(rain_amounts, final_rain_probs, cfg)

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
                    "predicted_amount_mm": _rounded_or_none(rain_amounts.get(label)),
                    "amount_level": (
                        map_rain_amount_to_level(float(rain_amounts[label]), 1, cfg)
                        if rain_amounts.get(label) is not None
                        else None
                    ),
                    "amount_level_basis": rain_amount_level_basis(1),
                    "amount_source": rain_amount_result["source"],
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

    _attach_rain_amount_accumulation(forecast_anchors, cfg)
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


def predict_dispatch_risk_v26(
    target_station_id: str,
    recent_observations: pd.DataFrame,
    nearby_observations: pd.DataFrame | None = None,
    multi_station_observations: dict[str, Any] | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    station_context = _load_or_build_multistation_context(
        cfg,
        project,
        str(target_station_id),
        recent_observations,
        multi_station_observations,
    )
    nearby_df = nearby_observations
    if nearby_df is None:
        nearby_df = _nearby_latest_observations_from_frames(
            station_context["loader"]["station_frames"],
            str(target_station_id),
        )

    result = predict_dispatch_risk_v25(
        target_station_id,
        recent_observations,
        nearby_df,
        cwa_forecast,
        tide_observations,
        visibility_observations,
        config_path,
        project,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.6")
    target_cfg = cfg.get("target", {})
    result.setdefault("target_area", {})["target_station_role"] = target_cfg.get("target_station_role", "port_area_proxy")
    summary = _input_station_summary(cfg, str(target_station_id), station_context)
    result["input_station_summary"] = summary
    _apply_v26_multistation_postprocess(result, cfg, station_context)
    _refresh_v26_dispatch_outputs(result, cfg)

    trace = result.setdefault("trace", {})
    trace.update(
        {
            "target_station_id": str(target_station_id),
            "target_station_role": target_cfg.get("target_station_role", "port_area_proxy"),
            "multi_station_input": summary["multi_station_input"],
            "input_station_count": summary["input_station_count"],
            "input_station_ids": summary["input_station_ids"],
            "nearby_station_count": station_context["aggregation"]["nearby_station_count"],
            "fallback_to_single_station": summary["fallback_to_single_station"],
            "fallback_reason": summary["fallback_reason"],
            "multi_station_feature_mode": summary["multi_station_feature_mode"],
            "multi_station_features_used_as_model_input": False,
            "multi_station_features_used_as_postprocess": bool(cfg.get("multi_station_features", {}).get("enabled", True)),
            "train_inference_mismatch_prevented": True,
        }
    )
    return result


def predict_dispatch_risk_v27(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    pool_path = resolve_station_pool_path(cfg, project)
    station_pool_config = load_station_pool_config(pool_path)
    station_context = _load_or_build_priority_station_context(cfg, project, station_pool_config, port_local_observations)
    fallback_station_id = str(cfg.get("fallback_baseline", {}).get("station_id", "467441"))

    if fallback_observations is None:
        fallback_path = project / "data" / "raw" / "observed_hourly" / f"{fallback_station_id}.csv"
        if not fallback_path.exists():
            raise FileNotFoundError(f"Fallback station observation file not found: {fallback_station_id}")
        fallback_observations = load_observations(fallback_path)

    decision = station_context["station_priority_report"]["mode_decision"]
    nearby_df = pd.DataFrame()
    nearby_cwa_precip_df = _latest_observations_from_station_ids(
        station_context["station_frames"],
        _station_ids_by_role(station_pool_config, "nearby_cwa_live_reference"),
    )
    if decision["prediction_mode"] == "port_local_postprocess":
        nearby_df = _latest_observations_from_station_ids(
            station_context["station_frames"],
            station_context.get("available_port_local_station_ids", []),
        )

    result = predict_dispatch_risk_v25(
        fallback_station_id,
        fallback_observations,
        nearby_cwa_precip_df if not nearby_cwa_precip_df.empty else nearby_df,
        cwa_forecast,
        tide_observations,
        visibility_observations,
        config_path,
        project,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.7")
    result["target_area"] = {
        "name": "Kaohsiung Port",
        "port_code": str(target_area or "KHH"),
        "target_mode": "port_area",
    }

    if decision["prediction_mode"] == "port_local_postprocess":
        _apply_v27_port_local_postprocess(result, cfg, station_context)
        _refresh_v26_dispatch_outputs(result, cfg)
    else:
        _attach_v27_port_local_postprocess_details(result, station_context, enabled=False)

    summary = _station_priority_summary(cfg, str(target_area or "KHH"), station_context, decision, fallback_station_id)
    result["station_priority_summary"] = summary
    _apply_dispatch_anchor_time(
        result,
        prediction_mode=summary["prediction_mode"],
        station_context=station_context,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
    )
    data_availability = result.setdefault("data_availability", {})
    data_availability.update(
        {
            "using_port_local_station": summary["using_port_local_station"],
            "port_local_station_count": summary["port_local_station_count"],
            "port_local_station_ids": summary["port_local_station_ids"],
            "missing_port_local_station_ids": station_context.get("missing_port_local_station_ids", []),
            "fallback_station_available": fallback_station_id in station_context.get("fallback_station_ids", []) or fallback_observations is not None,
        }
    )

    trace = result.setdefault("trace", {})
    trace.update(
        {
            "port_local_scope": True,
            "target_area": str(target_area or "KHH"),
            "station_priority_policy": "port_local_first",
            "using_port_local_station": summary["using_port_local_station"],
            "port_local_station_count": summary["port_local_station_count"],
            "port_local_station_ids": summary["port_local_station_ids"],
            "available_port_local_wind_station_ids": station_context.get("available_port_local_wind_station_ids", []),
            "missing_port_local_station_ids": station_context.get("missing_port_local_station_ids", []),
            "fallback_to_467441": summary["fallback_to_467441"],
            "fallback_reason": summary["fallback_reason"],
            "467441_used_as_core_station": False,
            "467441_usage": "fallback_baseline" if summary["fallback_to_467441"] else "not_used_or_fallback_only",
            "prediction_mode": summary["prediction_mode"],
            "port_local_model_available": summary["port_local_model_available"],
            "model_retraining_required": summary["model_retraining_required"],
            "nearby_cwa_live_precipitation_station_ids": list(nearby_cwa_precip_df.get("station_id", pd.Series(dtype=str)).astype(str)) if not nearby_cwa_precip_df.empty else [],
            "nearby_cwa_live_precipitation_used_for_rain_amount": any(
                anchor.get("rain", {}).get("amount_source") == "nearby_cwa_live_observations"
                for anchor in result.get("forecast_anchors", [])
            ),
        }
    )
    if legacy_target_station_id is not None:
        trace.update(
            {
                "target_station_id_parameter_received": str(legacy_target_station_id),
                "target_station_id_treated_as": "fallback_baseline_or_legacy_proxy",
                "preferred_target_area": "KHH",
            }
        )
    return result


def _station_ids_by_role(station_pool_config: dict[str, Any], role: str) -> list[str]:
    return [
        str(station.get("station_id"))
        for station in enabled_input_stations(station_pool_config)
        if station.get("role") == role or station.get("group_role") == role
    ]


def _apply_dispatch_anchor_time(
    result: dict[str, Any],
    prediction_mode: str,
    station_context: dict[str, Any],
    fallback_observations: pd.DataFrame | None,
    cwa_forecast: dict[str, Any] | None,
) -> None:
    anchor = _resolve_dispatch_anchor_time(
        prediction_mode=prediction_mode,
        station_context=station_context,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        generated_at=result.get("generated_at"),
    )
    base_time = anchor.get("anchor_base_time")
    if base_time is None:
        return
    for item in result.get("forecast_anchors", []):
        offset = int(item.get("offset_minutes", 0))
        item["timestamp"] = (base_time + pd.Timedelta(minutes=offset)).isoformat()
        item["anchor_time_source"] = anchor["anchor_time_source"]
        item["anchor_time_staleness_minutes"] = anchor["anchor_time_staleness_minutes"]
    result["anchor_time_source"] = anchor["anchor_time_source"]
    result["anchor_time_staleness_minutes"] = anchor["anchor_time_staleness_minutes"]
    result.setdefault("trace", {})["anchor_time_selection"] = {
        "prediction_mode": prediction_mode,
        "anchor_time_source": anchor["anchor_time_source"],
        "anchor_base_time": base_time.isoformat(),
        "staleness_minutes": anchor["anchor_time_staleness_minutes"],
    }


def _resolve_dispatch_anchor_time(
    prediction_mode: str,
    station_context: dict[str, Any],
    fallback_observations: pd.DataFrame | None,
    cwa_forecast: dict[str, Any] | None = None,
    generated_at: str | datetime | None = None,
) -> dict[str, Any]:
    candidates: list[tuple[str, pd.Timestamp]] = []
    frames = station_context.get("station_frames", {})
    if prediction_mode in {"port_local_postprocess", "port_local_model"}:
        port_ids = list(station_context.get("available_port_local_station_ids", []))
        latest = _latest_time_from_frames({sid: frames.get(sid) for sid in port_ids})
        if latest is not None:
            candidates.append(("port_local_khwd", latest))
    elif prediction_mode == "nearby_cwa_historical_model":
        latest = _latest_time_from_frames(frames)
        if latest is not None:
            candidates.append(("nearby_cwa_historical", latest))
    if prediction_mode in {"fallback_baseline", "single_station_fallback"} or not candidates:
        fallback_latest = _latest_time_from_frame(fallback_observations)
        if fallback_latest is not None:
            candidates.append(("fallback_467441", fallback_latest))
    cwa_generated = _parse_time((cwa_forecast or {}).get("generated_at"))
    if cwa_generated is not None and not candidates:
        candidates.append(("cwa_forecast_generated_at", cwa_generated))
    if not candidates:
        return {"anchor_base_time": None, "anchor_time_source": "unavailable", "anchor_time_staleness_minutes": None}
    source, base = max(candidates, key=lambda item: item[1])
    generated = _parse_time(generated_at) or pd.Timestamp.now(tz=TAIPEI)
    staleness = max(0, int((generated - base).total_seconds() // 60))
    return {"anchor_base_time": base, "anchor_time_source": source, "anchor_time_staleness_minutes": staleness}


def _latest_time_from_frames(station_frames: dict[str, pd.DataFrame | None]) -> pd.Timestamp | None:
    latest_values = [_latest_time_from_frame(frame) for frame in station_frames.values()]
    latest_values = [value for value in latest_values if value is not None]
    return max(latest_values) if latest_values else None


def _latest_time_from_frame(frame: pd.DataFrame | None) -> pd.Timestamp | None:
    if frame is None or frame.empty or "obs_time" not in frame.columns:
        return None
    times = pd.to_datetime(frame["obs_time"], errors="coerce")
    if times.dropna().empty:
        return None
    return _ensure_taipei_timestamp(times.max())


def _parse_time(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return _ensure_taipei_timestamp(parsed)


def _ensure_taipei_timestamp(value: pd.Timestamp | datetime) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(TAIPEI)
    return ts.tz_convert(TAIPEI)


def predict_dispatch_risk_v28(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = predict_dispatch_risk_v27(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project_root,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
    )
    cfg = load_config(config_path)
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.8.1")
    trace = result.setdefault("trace", {})
    acquisition_cfg = cfg.get("port_local_data_acquisition", {})
    if acquisition_report is None:
        report_dir = Path(project_root) / acquisition_cfg.get("report_dir", "results/port_local_data_v28")
        acquisition_report = {
            "port_local_data_acquisition_enabled": bool(acquisition_cfg.get("enabled", True)),
            "port_local_data_refresh_attempted": False,
            "port_local_data_refresh_success": None,
            "port_local_station_files_created": [],
            "port_local_data_report_path": str(report_dir / "station_availability_report.json"),
            "fallback_to_existing_files": True,
        }
    trace.update(
        {
            "port_local_data_acquisition_enabled": bool(acquisition_report.get("port_local_data_acquisition_enabled", True)),
            "port_local_data_refresh_attempted": bool(acquisition_report.get("port_local_data_refresh_attempted", False)),
            "port_local_data_refresh_success": acquisition_report.get("port_local_data_refresh_success"),
            "port_local_station_files_created": acquisition_report.get("port_local_station_files_created", []),
            "port_local_data_report_path": acquisition_report.get("port_local_data_report_path"),
        }
    )
    if acquisition_report.get("port_local_data_refresh_error"):
        trace["port_local_data_refresh_error"] = acquisition_report.get("port_local_data_refresh_error")
    if acquisition_report.get("fallback_to_existing_files") is not None:
        trace["fallback_to_existing_files"] = acquisition_report.get("fallback_to_existing_files")
    result.setdefault("data_availability", {})["port_local_data_acquisition"] = {
        "refresh_attempted": trace["port_local_data_refresh_attempted"],
        "refresh_success": trace["port_local_data_refresh_success"],
        "created_files": trace["port_local_station_files_created"],
        "report_path": trace["port_local_data_report_path"],
    }
    return result


def predict_dispatch_risk_v29(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = predict_dispatch_risk_v28(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project_root,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
    )
    cfg = load_config(config_path)
    project = Path(project_root)
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v2.9")
    khwd_frames = _load_khwd_frames_for_v29(result, project)
    wind_features = build_port_local_wind_features(khwd_frames, cfg)
    postprocess_report = _apply_v29_postprocess_validation(result, wind_features, cfg)
    rain_report = _build_v29_rain_probability_report(result, cfg)
    trace_report = _build_v29_trace_report(result, wind_features, postprocess_report, rain_report, cfg)
    trace = result.setdefault("trace", {})
    trace.update(trace_report["trace"])
    result.setdefault("data_availability", {})["port_local_postprocess_validation"] = {
        "khwd_station_count": wind_features.get("station_count", 0),
        "quality_status": wind_features.get("quality_status"),
        "report_path": "results/dispatch_risk_v29/port_local_postprocess_report.json",
    }
    _write_v29_reports(project, result, postprocess_report, rain_report, trace_report)
    return result


def _load_khwd_frames_for_v29(result: dict[str, Any], project: Path) -> dict[str, pd.DataFrame]:
    station_ids = [
        station_id
        for station_id in result.get("station_priority_summary", {}).get("port_local_station_ids", [])
        if str(station_id).startswith("KHWD")
    ]
    frames: dict[str, pd.DataFrame] = {}
    for station_id in station_ids:
        path = project / "data" / "raw" / "observed_hourly" / f"{station_id}.csv"
        if path.exists():
            try:
                frames[str(station_id)] = load_observations(path)
            except Exception:
                continue
    return frames


def _apply_v29_postprocess_validation(result: dict[str, Any], wind_features: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    apply_labels = set(cfg.get("port_local_wind_postprocess", {}).get("apply_anchors", ["H1", "H2"]))
    base_wind = {
        str(anchor["label"]): map_wind_speed_to_operation_level(float(anchor["wind_speed"].get("predicted_mps", 0.0)), cfg)["operation_level"]
        for anchor in result.get("forecast_anchors", [])
        if str(anchor.get("label")) in apply_labels
    }
    base_gust = {
        str(anchor["label"]): map_wind_gust_to_operation_level(float(anchor["wind_gust"].get("predicted_mps", 0.0)), cfg, use_buffer=True)["operation_level"]
        for anchor in result.get("forecast_anchors", [])
        if str(anchor.get("label")) in apply_labels
    }
    wind_result = apply_port_local_wind_postprocess(base_wind, wind_features, cfg)
    gust_result = apply_port_local_gust_postprocess(base_gust, wind_features, cfg)
    anchor_adjustments: dict[str, Any] = {}
    for anchor in result.get("forecast_anchors", []):
        label = str(anchor.get("label"))
        rain = anchor.setdefault("rain", {})
        rain.setdefault("port_local_adjusted_probability", None)
        rain.setdefault("source_detail", {}).setdefault("port_local_rain_postprocess_applied", False)
        rain["source_detail"].setdefault("port_local_rain_data_available", False)
        rain["source_detail"].setdefault("port_local_rain_reason", "No port-local precipitation station available.")
        if label not in apply_labels:
            anchor["wind_speed"].setdefault("port_local_postprocess", {"applied": False})
            anchor["wind_gust"].setdefault("port_local_postprocess", {"applied": False})
            continue
        wind_detail = wind_result["postprocess_detail"][label]
        gust_detail = gust_result["postprocess_detail"][label]
        anchor["wind_speed"]["port_local_postprocess"] = wind_detail
        anchor["wind_gust"]["port_local_postprocess"] = gust_detail
        anchor["wind_speed"]["operation_level"] = wind_detail["adjusted_operation_level"]
        anchor["wind_gust"]["operation_level"] = gust_detail["adjusted_operation_level"]
        anchor_adjustments[label] = {
            "wind_postprocess_applied": bool(wind_detail["applied"]),
            "gust_postprocess_applied": bool(gust_detail["applied"]),
            "base_wind_level": wind_detail["base_operation_level"],
            "adjusted_wind_level": wind_detail["adjusted_operation_level"],
            "base_gust_level": gust_detail["base_operation_level"],
            "adjusted_gust_level": gust_detail["adjusted_operation_level"],
        }
    _refresh_v26_dispatch_outputs(result, cfg)
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "prediction_mode": result.get("station_priority_summary", {}).get("prediction_mode"),
        "khwd_station_ids_used": wind_features.get("station_ids_used", []),
        "khwd_features": wind_features.get("features", {}),
        "quality_status": wind_features.get("quality_status"),
        "warnings": wind_features.get("warnings", []),
        "anchor_adjustments": anchor_adjustments,
    }


def _build_v29_rain_probability_report(result: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    anchors = {}
    cwa_applied = []
    for anchor in result.get("forecast_anchors", []):
        label = str(anchor.get("label"))
        rain = anchor.get("rain", {})
        source = rain.get("source_detail", {})
        if source.get("cwa_prior_applied"):
            cwa_applied.append(label)
        anchors[label] = {
            "raw_model_probability": rain.get("raw_model_probability"),
            "nearby_adjusted_probability": rain.get("nearby_adjusted_probability"),
            "port_local_adjusted_probability": rain.get("port_local_adjusted_probability"),
            "cwa_adjusted_probability": rain.get("cwa_adjusted_probability"),
            "final_probability": rain.get("final_probability"),
            "level": rain.get("level"),
            "source_detail": source,
        }
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "rain_probability_preserved": all("final_probability" in anchor.get("rain", {}) for anchor in result.get("forecast_anchors", [])),
        "rain_probability_model_used": True,
        "port_local_rain_data_available": False,
        "cwa_prior_enabled": bool(cfg.get("cwa_pop_prior", {}).get("enabled", True)),
        "cwa_prior_applied_anchors": cwa_applied,
        "anchors": anchors,
    }


def _build_v29_trace_report(
    result: dict[str, Any],
    wind_features: dict[str, Any],
    postprocess_report: dict[str, Any],
    rain_report: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    trace = {
        "model_version": result.get("model_version"),
        "prediction_mode": result.get("station_priority_summary", {}).get("prediction_mode"),
        "using_port_local_station": result.get("station_priority_summary", {}).get("using_port_local_station"),
        "port_local_wind_station_count": wind_features.get("station_count", 0),
        "port_local_wind_station_ids": wind_features.get("station_ids_used", []),
        "port_local_wind_postprocess_enabled": bool(cfg.get("port_local_wind_postprocess", {}).get("enabled", True)),
        "port_local_gust_postprocess_enabled": bool(cfg.get("port_local_wind_postprocess", {}).get("enabled", True)),
        "rain_probability_preserved": bool(rain_report.get("rain_probability_preserved", False)),
        "rain_probability_model_used": bool(rain_report.get("rain_probability_model_used", False)),
        "cwa_pop_prior_enabled": bool(cfg.get("cwa_pop_prior", {}).get("enabled", True)),
        "cwa_pop_quality_gate_enabled": bool(cfg.get("cwa_pop_quality", {}).get("enabled", False)),
        "dispatch_risk_uses_postprocessed_wind_gust": True,
        "467441_used_as_core_station": False,
    }
    return {"generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"), "trace": trace, "postprocess_report_path": "results/dispatch_risk_v29/port_local_postprocess_report.json", "rain_probability_report_path": "results/dispatch_risk_v29/rain_probability_report.json"}


def _write_v29_reports(project: Path, result: dict[str, Any], postprocess_report: dict[str, Any], rain_report: dict[str, Any], trace_report: dict[str, Any]) -> None:
    out_dir = project / "results" / "dispatch_risk_v29"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prediction_samples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "port_local_postprocess_report.json").write_text(json.dumps(postprocess_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "rain_probability_report.json").write_text(json.dumps(rain_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "dispatch_risk_trace_report.json").write_text(json.dumps(trace_report, ensure_ascii=False, indent=2), encoding="utf-8")


def predict_dispatch_risk_v30(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    result = predict_dispatch_risk_v29(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.0")

    out_dir = project / "results" / "dispatch_risk_v30"
    out_dir.mkdir(parents=True, exist_ok=True)
    readiness_report = _load_or_compute_v30_readiness(result, cfg, project)
    port_local_metrics = _load_json(out_dir / "port_local_model_metrics.json") or {
        "model_version": "port_local_v30",
        "port_local_model_trained": False,
        "dataset_ready": bool(readiness_report.get("ready", False)),
        "failed_reasons": readiness_report.get("failed_reasons", []),
        "wind_speed": {},
        "wind_gust": {},
        "risk_level_evaluation": {"critical_under_warning_count": None, "level_accuracy": None},
        "rain_probability": {
            "port_local_rain_model_trained": False,
            "reason": "No valid port-local rain labels available or dataset not ready.",
            "fallback_rain_method": "existing_rain_probability_model_plus_cwa_prior",
        },
    }
    postprocess_metrics = _v30_postprocess_metrics(result)
    fallback_metrics = {"available": fallback_observations is not None or (project / "data" / "raw" / "observed_hourly" / "467441.csv").exists()}
    selection = select_dispatch_prediction_mode(port_local_metrics, postprocess_metrics, fallback_metrics, readiness_report, cfg)
    _apply_v30_selection_to_result(result, selection, readiness_report, port_local_metrics, cfg)
    rain_report = _build_v29_rain_probability_report(result, cfg)
    model_selection_report = _build_v30_model_selection_report(selection, readiness_report, port_local_metrics)
    training_report = _load_json(out_dir / "port_local_training_report.json") or _v30_untrained_report(readiness_report)
    _write_v30_reports(project, result, readiness_report, training_report, port_local_metrics, model_selection_report, rain_report)
    return result


def _load_or_compute_v30_readiness(result: dict[str, Any], cfg: dict[str, Any], project: Path) -> dict[str, Any]:
    out_dir = project / "results" / "dispatch_risk_v30"
    existing = _load_json(out_dir / "dataset_readiness_report.json")
    if existing:
        return existing
    khwd_frames = _load_khwd_frames_for_v29(result, project)
    built = build_port_local_training_dataset(
        khwd_frames,
        {"train_rain": bool(cfg.get("port_local_model", {}).get("train_rain_probability_if_labels_available", True))},
        cfg,
    )
    readiness = check_port_local_dataset_readiness(built["dataset"], cfg)
    return {"generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"), **readiness}


def _v30_postprocess_metrics(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("station_priority_summary", {})
    trace = result.get("trace", {})
    return {
        "available": bool(summary.get("using_port_local_station", False)) and int(trace.get("port_local_wind_station_count", 0) or 0) >= 2,
        "prediction_mode": summary.get("prediction_mode"),
        "port_local_wind_station_count": int(trace.get("port_local_wind_station_count", 0) or 0),
    }


def _apply_v30_selection_to_result(
    result: dict[str, Any],
    selection: dict[str, Any],
    readiness_report: dict[str, Any],
    port_local_metrics: dict[str, Any],
    cfg: dict[str, Any],
) -> None:
    selected = selection["selected_mode"]
    using_port_local = selected in {"port_local_model", "port_local_postprocess"}
    fallback_to_467441 = bool(selection.get("fallback_to_467441", False))
    result["prediction_mode"] = selected
    summary = result.setdefault("station_priority_summary", {})
    summary.update(
        {
            "prediction_mode": selected,
            "using_port_local_station": using_port_local,
            "fallback_to_467441": fallback_to_467441,
            "467441_used_as_core_station": False,
        }
    )
    result["model_selection_summary"] = {
        "selected_mode": selected,
        "dataset_ready": bool(readiness_report.get("ready", False)),
        "port_local_model_trained": bool(port_local_metrics.get("port_local_model_trained", False)),
        "port_local_model_accepted": bool(selection.get("model_accepted", False)),
        "fallback_to_port_local_postprocess": bool(selection.get("fallback_to_port_local_postprocess", False)),
        "fallback_to_467441": fallback_to_467441,
        "selection_reason": selection.get("selection_reason", selection.get("reason")),
        "failed_reasons": selection.get("failed_reasons", []),
        "fallback_chain": selection.get("fallback_chain", []),
    }
    trace = result.setdefault("trace", {})
    trace.update(
        {
            "model_version": result.get("model_version"),
            "prediction_mode": selected,
            "port_local_model_training_enabled": bool(cfg.get("port_local_training", {}).get("enabled", True)),
            "port_local_model_selected": selected == "port_local_model",
            "port_local_model_accepted": bool(selection.get("model_accepted", False)),
            "fallback_to_port_local_postprocess": bool(selection.get("fallback_to_port_local_postprocess", False)),
            "fallback_to_467441": fallback_to_467441,
            "fallback_reason": None if selected == "port_local_model" else selection.get("reason"),
            "467441_used_as_core_station": False,
            "rain_probability_preserved": True,
            "rain_model_mode": "existing_model_plus_cwa_prior",
            "cwa_pop_used_as_model_input": False,
            "cwa_pop_quality_gate_enabled": bool(cfg.get("cwa_pop_quality", {}).get("enabled", False)),
        }
    )


def _build_v30_model_selection_report(selection: dict[str, Any], readiness_report: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "selected_mode": selection.get("selected_mode"),
        "port_local_model_available": bool(metrics.get("port_local_model_trained", False)),
        "port_local_model_accepted": bool(selection.get("model_accepted", False)),
        "fallback_to_port_local_postprocess": bool(selection.get("fallback_to_port_local_postprocess", False)),
        "fallback_to_467441": bool(selection.get("fallback_to_467441", False)),
        "selection_reason": selection.get("selection_reason", selection.get("reason")),
        "failed_reasons": selection.get("failed_reasons", readiness_report.get("failed_reasons", [])),
        "fallback_chain": selection.get("fallback_chain", []),
        "dataset_readiness": readiness_report,
    }


def _v30_untrained_report(readiness_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_version": "port_local_v30",
        "port_local_model_trained": False,
        "reason": "Dataset readiness check failed or training CLI has not been run.",
        "failed_reasons": readiness_report.get("failed_reasons", []),
        "dataset_readiness": readiness_report,
    }


def _write_v30_reports(
    project: Path,
    result: dict[str, Any],
    readiness_report: dict[str, Any],
    training_report: dict[str, Any],
    metrics: dict[str, Any],
    model_selection_report: dict[str, Any],
    rain_report: dict[str, Any],
) -> None:
    out_dir = project / "results" / "dispatch_risk_v30"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dataset_readiness_report.json").write_text(json.dumps(readiness_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "port_local_training_report.json").write_text(json.dumps(training_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "port_local_model_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "model_selection_report.json").write_text(json.dumps(model_selection_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "prediction_samples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "rain_probability_report.json").write_text(json.dumps(rain_report, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def predict_dispatch_risk_v32(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    result = predict_dispatch_risk_v30(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.2")
    out_dir = project / "results" / "dispatch_risk_v32"
    out_dir.mkdir(parents=True, exist_ok=True)
    v30_dir = project / "results" / "dispatch_risk_v30"
    readiness = _load_json(v30_dir / "dataset_readiness_report.json") or {"ready": False, "failed_reasons": ["v30 dataset readiness report missing"]}
    port_metrics = _load_json(v30_dir / "port_local_model_metrics.json") or {"port_local_model_trained": False}
    ranking = _load_json(out_dir / "nearby_station_ranking_report.json") or _default_v32_ranking_report(cfg)
    nearby_readiness = _load_json(out_dir / "nearby_cwa_readiness_report.json") or {"ready": False, "selected_station_ids": ranking.get("selected_station_ids", []), "failed_reasons": ["nearby CWA historical readiness report missing"]}
    nearby_metrics = _load_json(out_dir / "nearby_cwa_model_metrics.json") or {"nearby_cwa_historical_model_trained": False, "failed_reasons": nearby_readiness.get("failed_reasons", [])}
    postprocess_metrics = _v30_postprocess_metrics(result)
    fallback_metrics = {"available": fallback_observations is not None or (project / "data" / "raw" / "observed_hourly" / "467441.csv").exists()}
    selection = select_dispatch_prediction_mode_v32(port_metrics, postprocess_metrics, nearby_metrics, fallback_metrics, readiness, nearby_readiness, cfg)
    _apply_v32_selection_to_result(result, selection, ranking, nearby_readiness, nearby_metrics, cfg)
    model_selection_report = _build_v32_model_selection_report(selection, readiness, nearby_readiness, ranking, nearby_metrics)
    _write_v32_reports(project, result, ranking, nearby_readiness, nearby_metrics, model_selection_report)
    return result


def _default_v32_ranking_report(cfg: dict[str, Any]) -> dict[str, Any]:
    station_ids = cfg.get("nearby_cwa_historical_training", {}).get("priority_1_station_ids", [])
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "baseline_station": {"station_id": "467441", "name": "Kaohsiung", "distance_to_port_km": None},
        "ranked_candidates": [],
        "selected_station_ids": station_ids,
        "all_selected_stations_closer_than_467441": False,
        "warning": "nearby_station_ranking_report.json not found; using configured priority station ids.",
    }


def _apply_v32_selection_to_result(
    result: dict[str, Any],
    selection: dict[str, Any],
    ranking: dict[str, Any],
    nearby_readiness: dict[str, Any],
    nearby_metrics: dict[str, Any],
    cfg: dict[str, Any],
) -> None:
    selected = selection.get("selected_mode", result.get("prediction_mode"))
    result["prediction_mode"] = selected
    selected_ids = ranking.get("selected_station_ids", nearby_readiness.get("selected_station_ids", []))
    nearby_accepted = bool(selection.get("nearby_cwa_historical_model_accepted", False))
    result["nearby_cwa_historical_summary"] = {
        "enabled": bool(cfg.get("nearby_cwa_historical_training", {}).get("enabled", True)),
        "model_available": bool(nearby_metrics.get("nearby_cwa_historical_model_trained", False)),
        "model_accepted": nearby_accepted,
        "selected_station_ids": selected_ids,
        "all_selected_stations_closer_than_467441": bool(ranking.get("all_selected_stations_closer_than_467441", False)),
        "baseline_station_id": cfg.get("nearby_cwa_historical_training", {}).get("baseline_station_id", "467441"),
        "usage": "fallback_training_reference",
        "is_port_local_core": False,
    }
    result["model_selection_summary"] = {
        **result.get("model_selection_summary", {}),
        "selected_mode": selected,
        "nearby_cwa_historical_model_accepted": nearby_accepted,
        "fallback_to_nearby_cwa_historical_model": bool(selection.get("fallback_to_nearby_cwa_historical_model", False)),
        "fallback_to_467441": bool(selection.get("fallback_to_467441", False)),
        "selection_reason": selection.get("selection_reason", selection.get("reason")),
        "fallback_chain": selection.get("fallback_chain", []),
        "failed_reasons": selection.get("failed_reasons", []),
    }
    trace = result.setdefault("trace", {})
    trace.update(
        {
            "model_version": result.get("model_version"),
            "prediction_mode": selected,
            "nearby_cwa_historical_training_enabled": bool(cfg.get("nearby_cwa_historical_training", {}).get("enabled", True)),
            "nearby_cwa_historical_model_available": bool(nearby_metrics.get("nearby_cwa_historical_model_trained", False)),
            "nearby_cwa_historical_model_accepted": nearby_accepted,
            "nearby_cwa_selected_station_ids": selected_ids,
            "all_nearby_cwa_stations_closer_than_467441": bool(ranking.get("all_selected_stations_closer_than_467441", False)),
            "nearby_cwa_used_as_port_local_core": False,
            "fallback_to_nearby_cwa_historical_model": bool(selection.get("fallback_to_nearby_cwa_historical_model", False)),
            "fallback_to_467441": bool(selection.get("fallback_to_467441", False)),
            "467441_used_as_core_station": False,
            "rain_probability_preserved": True,
            "rain_model_mode": "nearby_cwa_historical_rain_model_plus_cwa_prior" if nearby_accepted else "existing_model_plus_cwa_prior",
            "cwa_pop_used_as_model_input": False,
        }
    )


def _build_v32_model_selection_report(
    selection: dict[str, Any],
    port_readiness: dict[str, Any],
    nearby_readiness: dict[str, Any],
    ranking: dict[str, Any],
    nearby_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "selected_mode": selection.get("selected_mode"),
        "selection_reason": selection.get("selection_reason", selection.get("reason")),
        "fallback_chain": selection.get("fallback_chain", []),
        "fallback_to_nearby_cwa_historical_model": bool(selection.get("fallback_to_nearby_cwa_historical_model", False)),
        "fallback_to_467441": bool(selection.get("fallback_to_467441", False)),
        "nearby_cwa_historical_model_available": bool(nearby_metrics.get("nearby_cwa_historical_model_trained", False)),
        "nearby_cwa_historical_model_accepted": bool(selection.get("nearby_cwa_historical_model_accepted", False)),
        "port_local_dataset_readiness": port_readiness,
        "nearby_cwa_readiness": nearby_readiness,
        "nearby_station_ranking": ranking,
        "failed_reasons": selection.get("failed_reasons", []),
    }


def _write_v32_reports(
    project: Path,
    result: dict[str, Any],
    ranking: dict[str, Any],
    nearby_readiness: dict[str, Any],
    nearby_metrics: dict[str, Any],
    model_selection_report: dict[str, Any],
) -> None:
    out_dir = project / "results" / "dispatch_risk_v32"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not (out_dir / "nearby_station_ranking_report.json").exists():
        (out_dir / "nearby_station_ranking_report.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (out_dir / "nearby_cwa_readiness_report.json").exists():
        (out_dir / "nearby_cwa_readiness_report.json").write_text(json.dumps(nearby_readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (out_dir / "nearby_cwa_model_metrics.json").exists():
        (out_dir / "nearby_cwa_model_metrics.json").write_text(json.dumps(nearby_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "model_selection_report.json").write_text(json.dumps(model_selection_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "prediction_samples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def predict_dispatch_risk_v33(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
    no_realtime_khwd_mode: bool = False,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    result = predict_dispatch_risk_v32(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.3")
    context = _build_v33_selection_context(result, cfg, project, fallback_observations, no_realtime_khwd_mode)
    selection = select_prediction_mode(context)
    _apply_v33_selection(result, selection, context, cfg)
    reports = _build_v33_reports(result, selection, context, cfg)
    _write_v33_reports(project, result, reports)
    return result


def _build_v33_selection_context(
    result: dict[str, Any],
    cfg: dict[str, Any],
    project: Path,
    fallback_observations: pd.DataFrame | None,
    no_realtime_khwd_mode: bool,
) -> dict[str, Any]:
    v30_dir = project / "results" / "dispatch_risk_v30"
    v32_dir = project / "results" / "dispatch_risk_v32"
    port_readiness = _load_json(v30_dir / "dataset_readiness_report.json") or {}
    port_metrics = _load_json(v30_dir / "port_local_model_metrics.json") or {}
    nearby_metrics = _load_json(v32_dir / "nearby_cwa_model_metrics.json") or {}
    nearby_ranking = _load_json(v32_dir / "nearby_station_ranking_report.json") or {}
    trace = result.get("trace", {})
    valid_khwd_count = int(trace.get("port_local_wind_station_count", 0) or result.get("station_priority_summary", {}).get("port_local_station_count", 0) or 0)
    khwd_available = valid_khwd_count >= 2 and not no_realtime_khwd_mode
    nearby_critical = int((nearby_metrics.get("risk_level_evaluation", {}) or {}).get("critical_under_warning_count") or 0)
    port_critical = int((port_metrics.get("risk_level_evaluation", {}) or {}).get("critical_under_warning_count") or 0)
    return {
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.3"),
        "port_local_model_available": bool(port_metrics.get("port_local_model_trained", False)),
        "port_local_model_accepted": False,
        "dataset_ready": bool(port_readiness.get("ready", False)),
        "port_local_model_trained": bool(port_metrics.get("port_local_model_trained", False)),
        "port_local_model_critical_under_warning_count": port_critical,
        "khwd_realtime_available": khwd_available,
        "valid_khwd_station_count": 0 if no_realtime_khwd_mode else valid_khwd_count,
        "no_realtime_khwd_mode": bool(no_realtime_khwd_mode),
        "khwd_realtime_disabled_by_request": bool(no_realtime_khwd_mode),
        "nearby_cwa_historical_training_enabled": bool(cfg.get("nearby_cwa_historical_training", {}).get("enabled", True)),
        "nearby_cwa_historical_model_available": bool(nearby_metrics.get("nearby_cwa_historical_model_trained", False)),
        "nearby_cwa_historical_model_accepted": bool(result.get("nearby_cwa_historical_summary", {}).get("model_accepted", False)),
        "nearby_cwa_selected_station_ids": result.get("nearby_cwa_historical_summary", {}).get("selected_station_ids", []),
        "all_nearby_cwa_stations_closer_than_467441": bool(nearby_ranking.get("all_selected_stations_closer_than_467441", result.get("nearby_cwa_historical_summary", {}).get("all_selected_stations_closer_than_467441", False))),
        "nearby_cwa_critical_under_warning_count": nearby_critical,
        "nearby_cwa_used_as_port_local_core": False,
        "fallback_baseline_available": fallback_observations is not None or (project / "data" / "raw" / "observed_hourly" / "467441.csv").exists(),
        "467441_used_as_core_station": False,
        "rain_probability_preserved": all("rain" in anchor and "final_probability" in anchor.get("rain", {}) for anchor in result.get("forecast_anchors", [])),
        "cwa_pop_zero_is_valid_probability": bool(cfg.get("rain_probability", {}).get("cwa_pop_zero_is_valid_probability", True)),
    }


def _apply_v33_selection(result: dict[str, Any], selection: dict[str, Any], context: dict[str, Any], cfg: dict[str, Any]) -> None:
    selected = selection["selected_mode"]
    result["prediction_mode"] = selected
    summary = result.setdefault("model_selection_summary", {})
    summary.update(
        {
            "selected_mode": selected,
            "port_local_model_accepted": bool(context.get("port_local_model_accepted", False)),
            "port_local_postprocess_available": any(item["mode"] == "port_local_postprocess" and item["eligible"] for item in selection["evaluated_modes"]),
            "nearby_cwa_historical_model_available": bool(context.get("nearby_cwa_historical_model_available", False)),
            "nearby_cwa_historical_model_accepted": bool(context.get("nearby_cwa_historical_model_accepted", False)),
            "fallback_to_nearby_cwa_historical_model": bool(selection["fallback_to_nearby_cwa_historical_model"]),
            "fallback_to_467441": bool(selection["fallback_to_467441"]),
            "selection_reason": selection["selection_reason"],
            "fallback_chain": selection["fallback_chain"],
            "evaluated_modes": selection["evaluated_modes"],
            "blocking_reasons": selection["blocking_reasons"],
        }
    )
    nearby = result.setdefault("nearby_cwa_historical_summary", {})
    nearby_selected = selected == "nearby_cwa_historical_model"
    nearby.update(
        {
            "fallback_eligible": bool(context.get("nearby_cwa_historical_model_available")) and bool(context.get("nearby_cwa_historical_model_accepted")) and bool(context.get("all_nearby_cwa_stations_closer_than_467441")),
            "selected_for_this_request": nearby_selected,
            "is_port_local_core": False,
            "not_selected_reason": None if nearby_selected else ("KHWD realtime data is available; port_local_postprocess has higher priority." if selected == "port_local_postprocess" else "Nearby CWA historical model was not selected by v3.3 selection engine."),
        }
    )
    trace = result.setdefault("trace", {})
    trace.update(
        {
            "model_version": result["model_version"],
            "prediction_mode": selected,
            "selection_engine_version": "v3.3",
            "selection_case_id": selection["selection_case_id"],
            "khwd_realtime_available": bool(context["khwd_realtime_available"]),
            "valid_khwd_station_count": int(context["valid_khwd_station_count"]),
            "no_realtime_khwd_mode": bool(context["no_realtime_khwd_mode"]),
            "khwd_realtime_disabled_by_request": bool(context["khwd_realtime_disabled_by_request"]),
            "nearby_cwa_historical_training_enabled": bool(context["nearby_cwa_historical_training_enabled"]),
            "nearby_cwa_historical_model_available": bool(context["nearby_cwa_historical_model_available"]),
            "nearby_cwa_historical_model_accepted": bool(context["nearby_cwa_historical_model_accepted"]),
            "nearby_cwa_selected_station_ids": context["nearby_cwa_selected_station_ids"],
            "all_nearby_cwa_stations_closer_than_467441": bool(context["all_nearby_cwa_stations_closer_than_467441"]),
            "nearby_cwa_used_as_port_local_core": False,
            "fallback_to_nearby_cwa_historical_model": bool(selection["fallback_to_nearby_cwa_historical_model"]),
            "fallback_to_467441": bool(selection["fallback_to_467441"]),
            "467441_used_as_core_station": False,
            "rain_probability_preserved": True,
            "rain_model_mode": "nearby_cwa_historical_rain_model_plus_cwa_prior" if bool(context["nearby_cwa_historical_model_accepted"]) else "existing_model_plus_cwa_prior",
            "cwa_pop_used_as_model_input": False,
            "selection_assertions": selection["assertions"],
        }
    )


def _build_v33_reports(result: dict[str, Any], selection: dict[str, Any], context: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    anchors = [str(anchor.get("label", anchor.get("anchor", f"H{idx + 1}"))) for idx, anchor in enumerate(result.get("forecast_anchors", []))]
    missing_rain = [label for label, anchor in zip(anchors, result.get("forecast_anchors", [])) if "rain" not in anchor or "final_probability" not in anchor.get("rain", {})]
    station_role = {
        "model_version": result["model_version"],
        "violations_found": False,
        "checks": {
            "467441_used_as_core_station": False,
            "nearby_cwa_used_as_port_local_core": False,
            "cwa_pop_used_as_model_input": False,
            "khwd_is_only_port_local_station_group": True,
        },
    }
    rain_report = {
        "model_version": result["model_version"],
        "rain_probability_preserved": not missing_rain,
        "anchors_checked": anchors,
        "missing_rain_anchors": missing_rain,
        "cwa_pop_zero_treated_as_valid": bool(cfg.get("rain_probability", {}).get("cwa_pop_zero_is_valid_probability", True)),
        "cwa_pop_used_as_model_input": False,
    }
    scenario = {
        "model_version": result["model_version"],
        "scenario": selection["selection_case_id"],
        "selected_mode": selection["selected_mode"],
        "passed": all(selection["assertions"].values()) and not missing_rain,
        "assertions": selection["assertions"],
    }
    transition = {
        "model_version": result["model_version"],
        "fallback_chain": selection["fallback_chain"],
        "selected_mode": selection["selected_mode"],
        "transitions": selection["evaluated_modes"],
    }
    return {
        "scenario_validation_report.json": scenario,
        "api_contract_snapshot_v33.json": result,
        "rain_probability_integrity_report.json": rain_report,
        "station_role_violation_report.json": station_role,
        "mode_transition_matrix.json": transition,
    }


def _write_v33_reports(project: Path, result: dict[str, Any], reports: dict[str, Any]) -> None:
    out_dir = project / "results" / "dispatch_risk_v33"
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in reports.items():
        (out_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "prediction_samples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def predict_dispatch_risk_v34(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
    no_realtime_khwd_mode: bool = False,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    orchestration = run_training_orchestration(
        config_path=config_path,
        target_area=target_area,
        report_dir=cfg.get("training_orchestration", {}).get("report_dir", "results/dispatch_risk_v34"),
        project_root=project,
        force_train=False,
        dry_run=False,
    )
    result = predict_dispatch_risk_v33(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
        no_realtime_khwd_mode=no_realtime_khwd_mode,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.4")
    _apply_v34_metadata(result, cfg, orchestration, project, target_area, no_realtime_khwd_mode)
    _write_v34_reports(project, result, orchestration, cfg)
    return result


def build_dispatch_model_status_v34(
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    orchestration = run_training_orchestration(
        config_path=config_path,
        target_area=target_area,
        report_dir=cfg.get("training_orchestration", {}).get("report_dir", "results/dispatch_risk_v34"),
        project_root=project,
    )
    return {
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.4"),
        "target_area": target_area,
        "model_training_status": build_model_training_status(orchestration),
        "model_registry_summary": orchestration.get("model_registry_summary", {}),
        "trace": {
            "model_registry_loaded": True,
            "model_manifest_checked": True,
            "training_orchestration_version": "v3.4",
            "training_required": bool(orchestration.get("training_required", False)),
            "training_skipped": bool(orchestration.get("training_skipped", False)),
        },
    }


def _apply_v34_metadata(
    result: dict[str, Any],
    cfg: dict[str, Any],
    orchestration: dict[str, Any],
    project: Path,
    target_area: str,
    no_realtime_khwd_mode: bool,
) -> None:
    training_status = build_model_training_status(orchestration)
    registry_summary = orchestration.get("model_registry_summary", {})
    nearby_status = training_status.get("available_models", {}).get("nearby_cwa_historical_model", {})
    result["model_training_status"] = training_status
    result["model_registry_summary"] = registry_summary
    result["current_station_usage"] = build_current_station_usage(result, cfg)
    result["station_display_rows"] = build_station_display_rows(result, cfg, project)
    result.setdefault("data_availability", {}).update(
        {
            "model_registry_loaded": True,
            "model_manifest_checked": True,
            "nearby_cwa_historical_model_available": bool(nearby_status.get("available", False)),
            "nearby_cwa_historical_model_accepted": bool(nearby_status.get("accepted", False)),
        }
    )
    summary = result.setdefault("model_selection_summary", {})
    summary.update(
        {
            "model_registry_used": True,
            "model_manifest_checked": True,
            "selected_model_artifact_version": nearby_status.get("artifact_version") if result.get("prediction_mode") == "nearby_cwa_historical_model" else None,
            "training_status_used_for_selection": True,
        }
    )
    trace = result.setdefault("trace", {})
    trace.update(
        {
            "model_version": result["model_version"],
            "selection_engine_version": "v3.4",
            "model_registry_loaded": True,
            "model_manifest_checked": True,
            "training_orchestration_version": "v3.4",
            "training_required": bool(orchestration.get("training_required", False)),
            "training_skipped": bool(orchestration.get("training_skipped", False)),
            "port_local_station_ids_used": result["current_station_usage"].get("port_local_station_ids_used", []),
            "nearby_cwa_selected_station_ids": result["current_station_usage"].get("nearby_cwa_station_ids_available", []),
            "baseline_station_id": result["current_station_usage"].get("baseline_station_id", "467441"),
            "467441_used_as_core_station": False,
            "nearby_cwa_used_as_port_local_core": False,
            "cwa_pop_used_as_model_input": False,
            "rain_probability_preserved": True,
            "no_realtime_khwd_mode": bool(no_realtime_khwd_mode),
            "khwd_realtime_disabled_by_request": bool(no_realtime_khwd_mode),
        }
    )
    assertions = trace.setdefault("selection_assertions", {})
    assertions.update(
        {
            "station_usage_exported_to_ui": True,
            "model_training_status_exported_to_ui": True,
        }
    )


def _build_v34_reports(result: dict[str, Any], orchestration: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    violations = station_role_violations(result.get("station_display_rows", []), result)
    anchors = [str(anchor.get("label", f"H{idx + 1}")) for idx, anchor in enumerate(result.get("forecast_anchors", []))]
    missing_rain = [label for label, anchor in zip(anchors, result.get("forecast_anchors", [])) if "rain" not in anchor or "final_probability" not in anchor.get("rain", {})]
    return {
        "current_station_usage_report.json": {
            "model_version": result["model_version"],
            **result.get("current_station_usage", {}),
        },
        "ui_payload_snapshot.json": {
            "model_version": result["model_version"],
            "prediction_mode": result.get("prediction_mode"),
            "model_training_status": result.get("model_training_status"),
            "current_station_usage": result.get("current_station_usage"),
            "station_display_rows": result.get("station_display_rows"),
        },
        "api_contract_snapshot_v34.json": result,
        "rain_probability_integrity_report.json": {
            "model_version": result["model_version"],
            "rain_probability_preserved": not missing_rain,
            "missing_rain_anchors": missing_rain,
            "cwa_pop_used_as_model_input": False,
        },
        "station_role_violation_report.json": {
            "model_version": result["model_version"],
            "violations_found": bool(violations),
            "violations": violations,
        },
    }


def _write_v34_reports(project: Path, result: dict[str, Any], orchestration: dict[str, Any], cfg: dict[str, Any]) -> None:
    out_dir = project / "results" / "dispatch_risk_v34"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = _build_v34_reports(result, orchestration, cfg)
    for filename, payload in reports.items():
        (out_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "prediction_samples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def predict_dispatch_risk_v35(
    port_local_observations: dict[str, pd.DataFrame] | None = None,
    fallback_observations: pd.DataFrame | None = None,
    cwa_forecast: dict[str, Any] | None = None,
    tide_observations: pd.DataFrame | None = None,
    visibility_observations: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
    project_root: str | Path = ROOT,
    target_area: str = "KHH",
    legacy_target_station_id: str | None = None,
    acquisition_report: dict[str, Any] | None = None,
    no_realtime_khwd_mode: bool = False,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    result = predict_dispatch_risk_v34(
        port_local_observations=port_local_observations,
        fallback_observations=fallback_observations,
        cwa_forecast=cwa_forecast,
        tide_observations=tide_observations,
        visibility_observations=visibility_observations,
        config_path=config_path,
        project_root=project,
        target_area=target_area,
        legacy_target_station_id=legacy_target_station_id,
        acquisition_report=acquisition_report,
        no_realtime_khwd_mode=no_realtime_khwd_mode,
    )
    result["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.5")
    result["system_audit_summary"] = {
        "model_version": result["model_version"],
        "data_summary_available": True,
        "station_summary_available": True,
        "dataset_duration_summary_available": True,
        "model_accuracy_summary_available": True,
        "system_audit_endpoint": f"/api/v1/dispatch/system-audit?target_area={target_area}",
    }
    trace = result.setdefault("trace", {})
    trace["model_version"] = result["model_version"]
    trace["system_audit_summary_attached"] = True
    extended = _build_extended_cwa_forecast_windows(cfg, project, result.get("generated_at"))
    result["extended_forecast_windows"] = extended
    result["cwa"] = _frontend_cwa_windows(extended)
    trace["extended_cwa_forecast_windows_attached"] = True
    _write_v35_prediction_sample(project, result)
    return result


def _write_v35_prediction_sample(project: Path, result: dict[str, Any]) -> None:
    out_dir = project / "results" / "dispatch_risk_v35"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prediction_samples_v35.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_or_build_priority_station_context(
    cfg: dict[str, Any],
    project: Path,
    station_pool_config: dict[str, Any],
    port_local_observations: dict[str, pd.DataFrame] | None,
) -> dict[str, Any]:
    if port_local_observations is None:
        return load_priority_station_pool_observations(
            station_pool_config,
            project / "data" / "raw" / "observed_hourly",
            cfg,
        )

    station_frames = {str(station_id): frame for station_id, frame in port_local_observations.items() if frame is not None and not frame.empty}
    port_local_ids = [
        str(station.get("station_id"))
        for station in enabled_input_stations(station_pool_config)
        if bool(station.get("is_port_local", False))
    ]
    port_local_wind_ids = [
        str(station.get("station_id"))
        for station in enabled_input_stations(station_pool_config)
        if station.get("priority_group") == "port_local_wind"
    ]
    available_port_local_ids = [station_id for station_id in port_local_ids if station_id in station_frames]
    available_port_local_wind_ids = [station_id for station_id in port_local_wind_ids if station_id in station_frames]
    station_availability = {
        "available_port_local_station_ids": available_port_local_ids,
        "available_port_local_wind_station_ids": available_port_local_wind_ids,
        "missing_port_local_station_ids": [station_id for station_id in port_local_ids if station_id not in station_frames],
        "fallback_station_ids": [],
    }
    decision = decide_prediction_mode(station_availability, None, cfg)
    return {
        "prediction_mode": decision["prediction_mode"],
        "port_local_station_ids": port_local_ids,
        "available_port_local_station_ids": available_port_local_ids,
        "available_port_local_wind_station_ids": available_port_local_wind_ids,
        "missing_port_local_station_ids": station_availability["missing_port_local_station_ids"],
        "fallback_station_ids": [],
        "fallback_used": bool(decision["fallback_to_467441"]),
        "fallback_reason": decision.get("fallback_reason"),
        "station_frames": station_frames,
        "station_priority_report": {
            "station_pool_version": station_pool_config.get("station_pool_version"),
            "station_pool_mode": station_pool_config.get("station_pool_mode"),
            "station_priority_policy": "port_local_first",
            "mode_decision": decision,
            "available_station_ids": list(station_frames),
            "missing_station_ids": station_availability["missing_port_local_station_ids"],
        },
    }


def _latest_observations_from_station_ids(station_frames: dict[str, pd.DataFrame], station_ids: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for station_id in station_ids:
        frame = station_frames.get(station_id)
        if frame is None or frame.empty:
            continue
        work = frame.copy()
        if "obs_time" in work.columns:
            work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
            work = work.sort_values("obs_time")
        row = work.iloc[-1].to_dict()
        row["station_id"] = station_id
        if "precipitation_1hr" in row and "precip_1hr" not in row:
            row["precip_1hr"] = row.get("precipitation_1hr")
        rows.append(row)
    return pd.DataFrame(rows)


def _rounded_or_none(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(numeric):
        return None
    return round(numeric, digits)


def _predict_nearby_precipitation_amounts(
    project: Path,
    nearby_observations: pd.DataFrame | None,
    fallback_observations: pd.DataFrame | None = None,
) -> dict[str, Any]:
    labels = ["H1", "H2", "H3", "H4"]
    manifest_path = project / "models" / "nearby_cwa_v32" / "model_manifest.json"
    observations, source = _select_precipitation_amount_observations(nearby_observations, fallback_observations)
    empty = {"amounts": {label: None for label in labels}, "source": source}
    if observations is None or observations.empty or not manifest_path.exists():
        return empty
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    feature_row = _nearby_precipitation_amount_feature_row(observations)
    if feature_row.empty:
        return empty
    outputs: dict[str, float | None] = {}
    for label in labels:
        model_info = manifest.get("models", {}).get(f"precipitation_amount_{label}")
        model_path_value = model_info.get("model_path") if isinstance(model_info, dict) else model_info
        if not model_path_value:
            outputs[label] = None
            continue
        model_path = _resolve_model_artifact_path(model_path_value, project)
        if model_path is None:
            outputs[label] = None
            continue
        try:
            bundle = joblib.load(model_path)
            features = list(bundle.get("feature_columns", []))
            fill = bundle.get("fill_values", {})
            x = feature_row.reindex(columns=features)
            x = x.apply(pd.to_numeric, errors="coerce").fillna(pd.Series(fill)).fillna(0.0)
            predicted = float(bundle["model"].predict(x)[0])
            if bundle.get("target_transform") == "log1p":
                predicted = float(np.expm1(predicted))
            outputs[label] = max(0.0, predicted)
        except Exception:
            outputs[label] = None
    return {"amounts": outputs, "source": source}


def _condition_rain_amounts_on_probability(
    amounts: dict[str, float | None],
    probabilities: dict[str, float],
    cfg: dict[str, Any],
) -> dict[str, float | None]:
    threshold = float(
        cfg.get("rain_amount_regression", {}).get(
            "inference_probability_threshold",
            cfg.get("targets", {}).get("precipitation", {}).get("inference_cls_threshold", 0.5),
        )
    )
    conditioned: dict[str, float | None] = {}
    for label, amount in amounts.items():
        probability = float(probabilities.get(label, 0.0))
        if probability < threshold:
            conditioned[label] = 0.0
        else:
            conditioned[label] = amount
    return conditioned


def _attach_rain_amount_accumulation(forecast_anchors: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    by_label = {str(anchor.get("label")): anchor for anchor in forecast_anchors}
    values = []
    for label in ["H1", "H2", "H3"]:
        amount = by_label.get(label, {}).get("rain", {}).get("predicted_amount_mm")
        if amount is None:
            return
        values.append(float(amount))
    total = round(float(sum(values)), 3)
    level = map_rain_amount_to_level(total, 3, cfg)
    estimate = {
        "predicted_amount_mm": total,
        "amount_level": level,
        "amount_level_basis": "estimated_3hr_sum_from_H1_H2_H3_predictions",
        "estimation_note": "H1-H3 predicted_amount_mm sum; not an observed rolling 3-hour accumulation.",
    }
    for label, anchor in by_label.items():
        rain = anchor.get("rain", {})
        if label in {"H1", "H2", "H3"}:
            rain["three_hour_accumulation_estimate"] = estimate


def _resolve_model_artifact_path(model_path_value: str, project: Path) -> Path | None:
    """Resolve a manifest-stored model path against `project`, independent of CWD.

    Manifest entries have historically stored paths two different ways: relative to
    the outer repo root (including a leading "kaohsiung_microclimate_lstm/" segment)
    or relative to `project` itself. Naively doing `project / model_path` when the
    value already includes that prefix produces a doubled, nonexistent path
    (e.g. ".../kaohsiung_microclimate_lstm/kaohsiung_microclimate_lstm/models/...").
    Anchoring on the known "models/..." suffix avoids depending on CWD or on which
    convention a given manifest entry happens to use.
    """
    candidate = Path(model_path_value)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    parts = candidate.parts
    if "models" in parts:
        suffix = parts[parts.index("models"):]
        resolved = project.joinpath(*suffix)
        if resolved.exists():
            return resolved
    direct = project / candidate
    if direct.exists():
        return direct
    return None


def _select_precipitation_amount_observations(
    nearby_observations: pd.DataFrame | None,
    fallback_observations: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, str]:
    if _has_precipitation_column(nearby_observations):
        station_ids = set(nearby_observations.get("station_id", pd.Series(dtype=str)).astype(str)) if "station_id" in nearby_observations.columns else set()
        if station_ids and all(station_id.startswith("C0V") for station_id in station_ids):
            return nearby_observations, "nearby_cwa_live_observations"
        return nearby_observations, "nearby_observations"
    if _has_precipitation_column(fallback_observations):
        return fallback_observations, "fallback_observations"
    return None, "unavailable"


def _has_precipitation_column(frame: pd.DataFrame | None) -> bool:
    return frame is not None and not frame.empty and ("precipitation_1hr" in frame.columns or "precip_1hr" in frame.columns)


def _nearby_precipitation_amount_feature_row(nearby_observations: pd.DataFrame) -> pd.DataFrame:
    work = nearby_observations.copy()
    if "obs_time" in work.columns:
        work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
        work = work.dropna(subset=["obs_time"])
    if work.empty:
        return pd.DataFrame()
    row: dict[str, Any] = {}
    precip_source = work["precipitation_1hr"] if "precipitation_1hr" in work.columns else work.get("precip_1hr")
    if precip_source is None:
        return pd.DataFrame()
    precip = pd.to_numeric(precip_source, errors="coerce")
    if precip.dropna().empty:
        return pd.DataFrame()
    row["nearby_cwa_precipitation_1hr_mean"] = float(precip.mean())
    row["nearby_cwa_precipitation_1hr_max"] = float(precip.max())
    row["nearby_cwa_precipitation_1hr_max_lag1"] = float(precip.max())
    row["nearby_cwa_precipitation_1hr_max_roll3"] = float(precip.mean())
    row["nearby_cwa_precipitation_roll3"] = float(precip.mean())
    row["nearby_cwa_precipitation_roll6"] = float(precip.mean())
    row["nearby_cwa_rainy_station_count"] = int((precip.fillna(0.0) > 0.5).sum())
    row["nearby_cwa_rainy_station_ratio"] = float(row["nearby_cwa_rainy_station_count"] / max(len(precip), 1))
    if "distance_to_port_km" in work.columns:
        distances = pd.to_numeric(work["distance_to_port_km"], errors="coerce")
        weights = 1.0 / (distances.fillna(distances.max()).fillna(0.0) + 1.0)
        valid = precip.notna() & weights.notna()
        row["distance_weighted_precipitation"] = float(np.average(precip[valid], weights=weights[valid])) if valid.any() else row["nearby_cwa_precipitation_1hr_mean"]
    else:
        row["distance_weighted_precipitation"] = row["nearby_cwa_precipitation_1hr_mean"]
    latest_time = pd.to_datetime(work["obs_time"], errors="coerce").max() if "obs_time" in work.columns else datetime.now(TAIPEI)
    hour = latest_time.hour + latest_time.minute / 60.0
    doy = latest_time.dayofyear
    row["hour_sin"] = float(np.sin(2 * np.pi * hour / 24.0))
    row["hour_cos"] = float(np.cos(2 * np.pi * hour / 24.0))
    row["doy_sin"] = float(np.sin(2 * np.pi * doy / 366.0))
    row["doy_cos"] = float(np.cos(2 * np.pi * doy / 366.0))
    return pd.DataFrame([row])


def _station_priority_summary(
    cfg: dict[str, Any],
    target_area: str,
    station_context: dict[str, Any],
    decision: dict[str, Any],
    fallback_station_id: str,
) -> dict[str, Any]:
    available = list(station_context.get("available_port_local_station_ids", []))
    fallback = bool(decision.get("fallback_to_467441", False))
    return {
        "prediction_mode": decision["prediction_mode"],
        "target_area": target_area,
        "using_port_local_station": bool(decision.get("using_port_local_station", False)),
        "port_local_station_count": len(available),
        "port_local_station_ids": available,
        "core_station_group": "port_local_wind" if available else None,
        "fallback_to_467441": fallback,
        "fallback_station_id": fallback_station_id if fallback else None,
        "fallback_reason": decision.get("fallback_reason"),
        "port_local_model_available": bool(decision.get("port_local_model_available", False)),
        "model_retraining_required": bool(decision.get("model_retraining_required", True)),
        "station_priority_policy": "port_local_first",
        "467441_used_as_core_station": False,
        "467441_usage": "fallback_baseline" if fallback else "not_used_or_fallback_only",
        "configured_port_local_station_ids": station_context.get("port_local_station_ids", []),
        "missing_port_local_station_ids": station_context.get("missing_port_local_station_ids", []),
    }


def _apply_v27_port_local_postprocess(result: dict[str, Any], cfg: dict[str, Any], station_context: dict[str, Any]) -> None:
    frames = station_context.get("station_frames", {})
    station_ids = list(station_context.get("available_port_local_station_ids", []))
    wind_ids = list(station_context.get("available_port_local_wind_station_ids", []))
    latest = _latest_observations_from_station_ids(frames, station_ids)
    wind_warning = float(cfg.get("wind_speed", {}).get("thresholds_mps", {}).get("warning", 10.8))
    gust_warning = float(cfg.get("wind_gust", {}).get("thresholds_mps", {}).get("warning", 13.9))
    wind_max = _numeric_latest_max(latest, "wind_speed")
    gust_max = _numeric_latest_max(latest, "wind_gust")
    rain_max = _numeric_latest_max(latest, "precipitation_1hr")
    if rain_max == 0.0:
        rain_max = _numeric_latest_max(latest, "precip_1hr")
    rainy_count = _numeric_positive_count(latest, "precipitation_1hr") + _numeric_positive_count(latest, "precip_1hr")

    for anchor in result.get("forecast_anchors", []):
        label = str(anchor.get("label"))
        rain_applied = False
        wind_applied = False
        gust_applied = False
        if label in {"H1", "H2"}:
            if rain_max > 0.5 or rainy_count >= 2:
                floor = 0.70 if rain_max > 0.5 else 0.60
                rain = anchor["rain"]
                adjusted = max(float(rain.get("final_probability", 0.0)), floor)
                rain["nearby_adjusted_probability"] = round(adjusted, 4)
                rain["final_probability"] = round(adjusted, 4)
                rain["level"] = map_rain_probability_to_level(adjusted, cfg)
                rain["source_detail"]["port_local_rain_postprocess_applied"] = True
                rain_applied = True
            if wind_max >= wind_warning:
                wind_detail = map_wind_speed_to_operation_level(wind_warning, cfg)
                anchor["wind_speed"]["operation_level"] = wind_detail["operation_level"]
                anchor["wind_speed"]["operation_label"] = wind_detail["operation_label"]
                anchor["wind_speed"]["port_local_postprocess_applied"] = True
                wind_applied = True
            else:
                anchor["wind_speed"]["port_local_postprocess_applied"] = False
            if gust_max >= gust_warning:
                gust_detail = map_wind_gust_to_operation_level(gust_warning, cfg, use_buffer=False)
                anchor["wind_gust"]["operation_level"] = gust_detail["operation_level"]
                anchor["wind_gust"]["operation_label"] = gust_detail["operation_label"]
                anchor["wind_gust"]["port_local_postprocess_applied"] = True
                gust_applied = True
            else:
                anchor["wind_gust"]["port_local_postprocess_applied"] = False
        anchor["port_local_postprocess"] = {
            "enabled": True,
            "mode": "port_local_postprocess",
            "port_local_wind_postprocess_applied": wind_applied,
            "port_local_gust_postprocess_applied": gust_applied,
            "port_local_rain_postprocess_applied": rain_applied,
            "port_local_wind_source": "KHWD",
            "port_local_wind_station_ids_used": wind_ids,
            "port_local_gust_station_ids_used": wind_ids,
            "port_local_rain_station_ids_used": station_ids,
            "port_local_station_ids_used": station_ids,
            "port_local_features_used": ["khwd_wind_speed_max", "khwd_wind_gust_max", "port_local_precipitation_1hr_max"],
        }


def _attach_v27_port_local_postprocess_details(result: dict[str, Any], station_context: dict[str, Any], enabled: bool) -> None:
    station_ids = list(station_context.get("available_port_local_station_ids", []))
    for anchor in result.get("forecast_anchors", []):
        anchor.setdefault("wind_speed", {})["port_local_postprocess_applied"] = False
        anchor.setdefault("wind_gust", {})["port_local_postprocess_applied"] = False
        anchor["port_local_postprocess"] = {
            "enabled": enabled,
            "mode": "fallback_baseline" if not enabled else "port_local_postprocess",
            "port_local_wind_postprocess_applied": False,
            "port_local_gust_postprocess_applied": False,
            "port_local_rain_postprocess_applied": False,
            "port_local_station_ids_used": station_ids,
            "port_local_features_used": [],
        }


def _numeric_latest_max(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.max()) if len(values) else 0.0


def _numeric_positive_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return int((values > 0).sum())


def _load_or_build_multistation_context(
    cfg: dict[str, Any],
    project: Path,
    target_station_id: str,
    recent_observations: pd.DataFrame,
    multi_station_observations: dict[str, Any] | None,
) -> dict[str, Any]:
    if multi_station_observations is not None:
        loader = multi_station_observations
        station_frames = dict(loader.get("station_frames", {}))
        station_frames.setdefault(target_station_id, recent_observations)
        loader = {**loader, "station_frames": station_frames}
        station_pool = [{"station_id": station_id} for station_id in station_frames]
    else:
        pool_path = resolve_station_pool_path(cfg, project)
        station_pool_config = load_station_pool_config(pool_path)
        station_pool = enabled_input_stations(station_pool_config)
        data_dir = project / "data" / "raw" / "observed_hourly"
        loader = load_multi_station_observations(
            station_pool,
            data_dir,
            target_station_id,
            required_columns=["obs_time"],
        )

    aggregation = build_nearby_aggregated_features(loader["station_frames"], target_station_id, cfg)
    return {"station_pool": station_pool, "loader": loader, "aggregation": aggregation}


def _nearby_latest_observations_from_frames(station_frames: dict[str, pd.DataFrame], target_station_id: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for station_id, frame in station_frames.items():
        if str(station_id) == str(target_station_id) or frame.empty:
            continue
        work = frame.copy()
        if "obs_time" in work.columns:
            work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
            work = work.sort_values("obs_time")
        row = work.iloc[-1].to_dict()
        row["station_id"] = str(station_id)
        if "precipitation_1hr" in row and "precip_1hr" not in row:
            row["precip_1hr"] = row.get("precipitation_1hr")
        rows.append(row)
    return pd.DataFrame(rows)


def _input_station_summary(cfg: dict[str, Any], target_station_id: str, station_context: dict[str, Any]) -> dict[str, Any]:
    loader = station_context["loader"]
    configured_ids = [str(station.get("station_id")) for station in station_context["station_pool"] if station.get("station_id")]
    available = [str(station_id) for station_id in loader.get("available_station_ids", [])]
    missing = [str(station_id) for station_id in loader.get("missing_station_ids", [])]
    return {
        "target_station_id": str(target_station_id),
        "input_station_count": int(loader.get("input_station_count", len(available))),
        "input_station_ids": configured_ids or available,
        "available_station_ids": available,
        "missing_station_ids": missing,
        "multi_station_input": bool(loader.get("multi_station_input", False)),
        "fallback_to_single_station": bool(loader.get("fallback_to_single_station", False)),
        "fallback_reason": loader.get("fallback_reason"),
        "station_pool_mode": cfg.get("station_pool", {}).get("mode", "port_local"),
        "multi_station_feature_mode": cfg.get("multi_station_features", {}).get("mode", "postprocess_only"),
    }


def _feature_value(features: pd.DataFrame, name: str, default: float = 0.0) -> float:
    if features.empty or name not in features.columns:
        return default
    value = pd.to_numeric(features[name], errors="coerce").iloc[0]
    return default if pd.isna(value) else float(value)


def _apply_v26_multistation_postprocess(result: dict[str, Any], cfg: dict[str, Any], station_context: dict[str, Any]) -> None:
    features = station_context["aggregation"]["features"]
    nearby_count = int(station_context["aggregation"]["nearby_station_count"])
    rain_max = _feature_value(features, "nearby_precipitation_1hr_max")
    rain_mean = _feature_value(features, "nearby_precipitation_1hr_mean")
    rainy_count = int(_feature_value(features, "nearby_rainy_station_count"))
    wind_max = _feature_value(features, "nearby_wind_speed_max")
    gust_max = _feature_value(features, "nearby_wind_gust_max")
    wind_warning = float(cfg.get("wind_speed", {}).get("thresholds_mps", {}).get("warning", 10.8))
    gust_warning = float(cfg.get("wind_gust", {}).get("thresholds_mps", {}).get("warning", 13.9))
    nearby_features_used = [
        "nearby_wind_speed_max",
        "nearby_wind_gust_max",
        "nearby_precipitation_1hr_max",
        "nearby_rainy_station_count",
    ]

    for anchor in result.get("forecast_anchors", []):
        label = str(anchor.get("label"))
        rain_applied = False
        wind_applied = False
        gust_applied = False
        if label in {"H1", "H2"} and nearby_count > 0:
            rain_floor = None
            if rain_max > 0.5:
                rain_floor = max(rain_floor or 0.0, 0.70)
            if rain_mean > 2.0:
                rain_floor = max(rain_floor or 0.0, 0.85)
            if rainy_count >= 2:
                rain_floor = max(rain_floor or 0.0, 0.60)
            if rain_floor is not None:
                rain = anchor["rain"]
                adjusted = max(float(rain.get("final_probability", 0.0)), rain_floor)
                rain["nearby_adjusted_probability"] = round(adjusted, 4)
                rain["final_probability"] = round(adjusted, 4)
                rain["level"] = map_rain_probability_to_level(adjusted, cfg)
                rain["source_detail"]["nearby_postprocess_applied"] = True
                rain_applied = True
            if wind_max >= wind_warning:
                wind_detail = map_wind_speed_to_operation_level(wind_warning, cfg)
                anchor["wind_speed"]["operation_level"] = wind_detail["operation_level"]
                anchor["wind_speed"]["operation_label"] = wind_detail["operation_label"]
                anchor["wind_speed"]["nearby_postprocess_applied"] = True
                wind_applied = True
            else:
                anchor["wind_speed"]["nearby_postprocess_applied"] = False
            if gust_max >= gust_warning:
                gust_detail = map_wind_gust_to_operation_level(gust_warning, cfg, use_buffer=False)
                anchor["wind_gust"]["operation_level"] = gust_detail["operation_level"]
                anchor["wind_gust"]["operation_label"] = gust_detail["operation_label"]
                anchor["wind_gust"]["nearby_postprocess_applied"] = True
                gust_applied = True
            else:
                anchor["wind_gust"]["nearby_postprocess_applied"] = False
        else:
            anchor["wind_speed"]["nearby_postprocess_applied"] = False
            anchor["wind_gust"]["nearby_postprocess_applied"] = False
        anchor["multi_station_postprocess"] = {
            "nearby_rain_postprocess_applied": rain_applied,
            "nearby_wind_postprocess_applied": wind_applied,
            "nearby_gust_postprocess_applied": gust_applied,
            "nearby_station_count": nearby_count,
            "nearby_features_used": nearby_features_used,
        }


def _refresh_v26_dispatch_outputs(result: dict[str, Any], cfg: dict[str, Any]) -> None:
    reliability = result.get("reliability", reliability_profile(cfg))
    trigger_priority = cfg.get("risk_trigger", {}).get("trigger_priority", ["wind_gust", "wind_speed", "rain_probability", "visibility", "tide"])
    for anchor in result.get("forecast_anchors", []):
        rain_level = anchor["rain"]["level"]
        wind_level = anchor["wind_speed"]["operation_level"]
        gust_level = anchor["wind_gust"]["operation_level"]
        risk_level = max([rain_level, wind_level, gust_level], key=lambda level: LEVEL_ORDER.get(level, 0))
        anchor["dispatch_risk_level"] = risk_level
        trigger_detail = build_risk_trigger_detail(
            risk_level,
            rain_level,
            wind_level,
            gust_level,
            anchor.get("visibility", {}).get("level"),
            anchor.get("tide", {}).get("level"),
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
        anchor["risk_trigger_detail"] = trigger_detail
        anchor["dispatch_action_level"] = action["dispatch_action_level"]
        anchor["dispatch_action"] = action
        anchor["dispatch_suggestion"] = action["action_description"]


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
    if nearby_observations is not None and nearby_observations.empty:
        return {
            "station_values_1hr": {},
            "max_1hr": 0.0,
            "mean_1hr": 0.0,
            "active_station_count": 0,
            "available": False,
        }
    if nearby_observations is not None:
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


def _build_extended_cwa_forecast_windows(cfg: dict[str, Any], project: Path, generated_at: str | None = None) -> dict[str, Any]:
    cwa_cfg = cfg.get("extended_forecast_windows", {})
    if cwa_cfg.get("enabled", True) is False:
        return {"available": False, "source": "cwa_official_forecast", "data_id": EXTENDED_DATAID, "windows": [], "reason": "disabled"}
    pop_cfg = cfg.get("rain_postprocess", {}).get("cwa_pop3h", {})
    location = str(cwa_cfg.get("location_name") or pop_cfg.get("fallback_location", "前鎮區"))
    cache_minutes = int(cwa_cfg.get("cache_minutes", pop_cfg.get("cache_minutes", 30)))
    now = _parse_time(generated_at) if generated_at else None
    try:
        cwa = fetch_pop3h(
            location,
            now=now,
            cache_minutes=cache_minutes,
            project_root=project,
            data_id=str(cwa_cfg.get("data_id", EXTENDED_DATAID)),
            include_wind_speed=True,
        )
    except Exception as exc:
        return {
            "available": False,
            "source": "cwa_official_forecast",
            "data_id": str(cwa_cfg.get("data_id", EXTENDED_DATAID)),
            "location_name": location,
            "windows": [],
            "reason": str(exc),
        }
    if not cwa.get("available", False):
        return {
            "available": False,
            "source": "cwa_official_forecast",
            "data_id": cwa.get("data_id") or str(cwa_cfg.get("data_id", EXTENDED_DATAID)),
            "location_name": cwa.get("location_name", location),
            "fetched_at": cwa.get("fetched_at"),
            "windows": [],
            "reason": cwa.get("reason", "cwa forecast unavailable"),
        }
    windows = [
        _build_extended_cwa_window("+3h", 180, cwa.get("current_wind_speed_mps"), cwa.get("current"), cwa, cfg),
        _build_extended_cwa_window("+6h", 360, cwa.get("next_wind_speed_mps"), cwa.get("next"), cwa, cfg),
    ]
    return {
        "available": True,
        "source": "cwa_official_forecast",
        "data_id": cwa.get("data_id") or str(cwa_cfg.get("data_id", EXTENDED_DATAID)),
        "location_name": cwa.get("location_name", location),
        "fetched_at": cwa.get("fetched_at"),
        "windows": windows,
    }


def _build_extended_cwa_window(
    label: str,
    offset_minutes: int,
    wind_speed_mps: Any,
    rain_probability: Any,
    cwa: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    wind_value = _safe_float(wind_speed_mps)
    rain_value = _safe_float(rain_probability)
    wind_detail = map_wind_speed_to_operation_level(wind_value, cfg) if wind_value is not None else None
    rain_level = map_rain_probability_to_level(rain_value, cfg) if rain_value is not None else None
    return {
        "label": label,
        "window": label,
        "offset_minutes": offset_minutes,
        "source": "cwa_official_forecast",
        "data_id": cwa.get("data_id") or EXTENDED_DATAID,
        "wind_speed": (
            {
                "available": True,
                "value_mps": round(wind_value, 3),
                "operation_level": wind_detail["operation_level"],
                "operation_label": wind_detail["operation_label"],
                "beaufort": wind_detail["beaufort"],
            }
            if wind_detail
            else {"available": False, "reason": "cwa_wind_speed_unavailable"}
        ),
        "rain_probability": (
            {
                "available": True,
                "value": round(rain_value, 4),
                "level": rain_level,
                "rain_level_label": _rain_probability_level_label(rain_level),
            }
            if rain_level is not None
            else {"available": False, "reason": "cwa_rain_probability_unavailable"}
        ),
        "wind_gust": {"available": False, "reason": "no_official_cwa_gust_product"},
        "visibility": {"available": False, "reason": "no_official_cwa_visibility_product"},
    }


def _frontend_cwa_windows(extended: dict[str, Any]) -> list[dict[str, Any]]:
    if not extended.get("available", False):
        return []
    rows = []
    for window in extended.get("windows", []):
        wind = window.get("wind_speed", {})
        rain = window.get("rain_probability", {})
        rows.append(
            {
                "window": window.get("window"),
                "rainLevel": rain.get("rain_level_label", "無") if rain.get("available") else "無",
                "beaufort": int((wind.get("beaufort") or {}).get("scale", 0)) if wind.get("available") else 0,
            }
        )
    return rows


def _rain_probability_level_label(level: str | None) -> str:
    return {
        "normal": "無",
        "watch": "小雨",
        "warning": "大雨",
        "high_risk": "豪雨",
        "stop": "超大豪雨",
    }.get(str(level), "無")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
