from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TAIPEI = timezone(timedelta(hours=8))
MODEL_VERSION = "kaohsiung_port_dispatch_risk_v3.4"
NEARBY_MODEL_FAMILY = "nearby_cwa_historical_model"
PORT_LOCAL_MODEL_FAMILY = "port_local_model"


def load_model_registry(project_root: str | Path) -> dict[str, Any]:
    project = Path(project_root)
    path = project / "models" / "model_registry.json"
    if not path.exists():
        return _empty_registry()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        registry = _empty_registry()
        registry["load_error"] = "invalid_json"
        return registry


def validate_model_manifest(manifest_path: str | Path, project_root: str | Path) -> dict[str, Any]:
    project = Path(project_root)
    path = Path(manifest_path)
    if not path.is_absolute() and not path.exists():
        path = project / path
    if not path.exists():
        return {"valid": False, "manifest_path": str(path), "reason": "manifest_missing"}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"valid": False, "manifest_path": str(path), "reason": "manifest_invalid_json"}

    missing_artifacts: list[str] = []
    for model_info in manifest.get("models", {}).values():
        if isinstance(model_info, dict):
            artifact = model_info.get("artifact_path")
        else:
            artifact = model_info
        if not artifact:
            continue
        artifact_path = Path(str(artifact))
        if not artifact_path.is_absolute() and not artifact_path.exists():
            artifact_path = project / artifact_path
        if not artifact_path.exists():
            missing_artifacts.append(str(artifact))

    accepted = bool(manifest.get("acceptance", {}).get("model_accepted", False))
    trained = bool(manifest.get("trained", False))
    critical = int(manifest.get("acceptance", {}).get("critical_under_warning_count", 0) or 0)
    valid = trained and accepted and critical == 0 and not missing_artifacts
    return {
        "valid": valid,
        "manifest_path": str(path),
        "manifest": manifest,
        "trained": trained,
        "accepted": accepted,
        "critical_under_warning_count": critical,
        "missing_artifacts": missing_artifacts,
        "reason": None if valid else _manifest_invalid_reason(trained, accepted, critical, missing_artifacts),
    }


def ensure_v34_registry_and_manifest(project_root: str | Path, config: dict[str, Any], target_area: str = "KHH") -> dict[str, Any]:
    project = Path(project_root)
    model_dir = project / "models" / "nearby_cwa_v34"
    manifest_path = model_dir / "model_manifest.json"
    if not manifest_path.exists():
        manifest = build_nearby_cwa_v34_manifest(project, config, target_area)
        if manifest["trained"]:
            model_dir.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    validation = validate_model_manifest(manifest_path, project)
    registry = build_model_registry(project, config, validation, target_area)
    registry_path = project / "models" / "model_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "registry": registry,
        "registry_path": str(registry_path),
        "nearby_manifest_validation": validation,
        "nearby_manifest_path": str(manifest_path),
    }


def build_model_registry(project: Path, config: dict[str, Any], nearby_validation: dict[str, Any], target_area: str) -> dict[str, Any]:
    generated_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
    nearby_manifest = nearby_validation.get("manifest", {})
    port_manifest_path = project / "models" / "port_local_v34" / "model_manifest.json"
    port_validation = validate_model_manifest(port_manifest_path, project)
    return {
        "registry_version": "v3.4",
        "model_version": config.get("project", {}).get("model_version", MODEL_VERSION),
        "target_area": target_area,
        "generated_at": generated_at,
        "models": {
            PORT_LOCAL_MODEL_FAMILY: {
                "model_family": PORT_LOCAL_MODEL_FAMILY,
                "artifact_version": "port_local_v34",
                "manifest_path": str(port_manifest_path),
                "trained": bool(port_validation.get("trained", False)),
                "available": bool(port_validation.get("valid", False)),
                "accepted": bool(port_validation.get("accepted", False)),
                "reason": port_validation.get("reason") or "Port-local historical dataset is not ready.",
            },
            NEARBY_MODEL_FAMILY: {
                "model_family": NEARBY_MODEL_FAMILY,
                "artifact_version": nearby_manifest.get("model_artifact_version", "nearby_cwa_v34"),
                "manifest_path": str(nearby_validation.get("manifest_path")),
                "trained": bool(nearby_validation.get("trained", False)),
                "available": bool(nearby_validation.get("valid", False)),
                "accepted": bool(nearby_validation.get("accepted", False)),
                "selected_station_ids": nearby_manifest.get("selected_station_ids", []),
                "all_selected_stations_closer_than_467441": bool(nearby_manifest.get("all_selected_stations_closer_than_467441", False)),
                "is_port_local_core": False,
                "reason": nearby_validation.get("reason"),
            },
        },
    }


def build_model_registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    models = registry.get("models", {})
    return {
        "model_registry_used": True,
        "registry_version": registry.get("registry_version", "v3.4"),
        "registry_path": "kaohsiung_microclimate_lstm/models/model_registry.json",
        "available_model_families": [
            family for family, item in models.items() if bool(item.get("available", False))
        ],
        "accepted_model_families": [
            family for family, item in models.items() if bool(item.get("accepted", False))
        ],
        "models": models,
    }


def build_nearby_cwa_v34_manifest(project: Path, config: dict[str, Any], target_area: str) -> dict[str, Any]:
    metrics_path = project / "results" / "dispatch_risk_v32" / "nearby_cwa_model_metrics.json"
    dataset_report_path = project / "results" / "dispatch_risk_v32" / "nearby_cwa_training_dataset_report.json"
    ranking_path = project / "results" / "dispatch_risk_v32" / "nearby_station_ranking_report.json"
    v32_manifest_path = project / "models" / "nearby_cwa_v32" / "model_manifest.json"
    metrics = _load_json(metrics_path)
    dataset_report = _load_json(dataset_report_path)
    ranking = _load_json(ranking_path)
    v32_manifest = _load_json(v32_manifest_path)
    selected = dataset_report.get("selected_station_ids") or ranking.get("selected_station_ids") or config.get("nearby_cwa_historical_training", {}).get("priority_1_station_ids", [])
    critical = int((metrics.get("risk_level_evaluation", {}) or {}).get("critical_under_warning_count") or 0)
    model_trained = bool(metrics.get("nearby_cwa_historical_model_trained", False)) and bool(v32_manifest.get("models"))
    accepted = model_trained and critical == 0
    readiness = dataset_report.get("readiness", {})
    model_entries = _group_v32_artifacts(project, v32_manifest.get("models", {}))
    return {
        "model_version": config.get("project", {}).get("model_version", MODEL_VERSION),
        "model_family": NEARBY_MODEL_FAMILY,
        "model_artifact_version": "nearby_cwa_v34",
        "artifact_source_version": "nearby_cwa_v32",
        "target_area": target_area,
        "trained": model_trained,
        "trained_at": datetime.now(TAIPEI).isoformat(timespec="seconds") if model_trained else None,
        "training_data_start": _training_start(project),
        "training_data_end": _training_end(project),
        "training_data_hash": _file_hash(project / "data" / "processed" / "nearby_cwa_training_dataset_v32.parquet"),
        "feature_schema_hash": _hash_json(dataset_report.get("feature_columns", v32_manifest.get("feature_columns", []))),
        "selected_station_ids": selected,
        "baseline_station_id": config.get("nearby_cwa_historical_training", {}).get("baseline_station_id", "467441"),
        "all_selected_stations_closer_than_467441": bool(ranking.get("all_selected_stations_closer_than_467441", True)),
        "is_port_local_core": False,
        "models": model_entries,
        "acceptance": {
            "model_accepted": accepted,
            "critical_under_warning_count": critical,
            "wind_speed_passed": _wind_speed_passed(metrics),
            "wind_gust_passed": _wind_gust_passed(metrics),
            "rain_probability_passed": _rain_passed(metrics),
        },
        "source_reports": {
            "metrics_path": str(metrics_path),
            "dataset_report_path": str(dataset_report_path),
            "ranking_path": str(ranking_path),
            "source_manifest_path": str(v32_manifest_path),
        },
        "readiness": readiness,
    }


def _group_v32_artifacts(project: Path, models: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, Any] = {
        "wind_speed": {"accepted": True, "artifacts": {}, "metrics_path": "kaohsiung_microclimate_lstm/results/dispatch_risk_v32/nearby_cwa_model_metrics.json"},
        "wind_gust": {"accepted": True, "artifacts": {}, "metrics_path": "kaohsiung_microclimate_lstm/results/dispatch_risk_v32/nearby_cwa_model_metrics.json"},
        "rain_probability": {"accepted": True, "artifacts": {}, "metrics_path": "kaohsiung_microclimate_lstm/results/dispatch_risk_v32/nearby_cwa_model_metrics.json"},
        "precipitation_amount": {"accepted": True, "artifacts": {}, "metrics_path": "kaohsiung_microclimate_lstm/results/dispatch_risk_v32/nearby_cwa_model_metrics.json"},
    }
    for key, raw_info in models.items():
        group = None
        if key.startswith("wind_speed"):
            group = "wind_speed"
        elif key.startswith("wind_gust"):
            group = "wind_gust"
        elif key.startswith("rain_probability"):
            group = "rain_probability"
        elif key.startswith("precipitation_amount"):
            group = "precipitation_amount"
        if group is None:
            continue
        artifact = _normalize_artifact_path(project, raw_info, key)
        artifact_info = {"artifact_path": artifact}
        if isinstance(raw_info, dict):
            if raw_info.get("algorithm"):
                artifact_info["algorithm"] = raw_info.get("algorithm")
            if raw_info.get("actual_estimator"):
                artifact_info["actual_estimator"] = raw_info.get("actual_estimator")
        grouped[group]["artifacts"][key] = artifact_info
        grouped[group].setdefault("artifact_path", artifact)
    return grouped


def _normalize_artifact_path(project: Path, raw_path: Any, key: str) -> str:
    if isinstance(raw_path, dict):
        raw_path = raw_path.get("artifact_path") or raw_path.get("model_path") or ""
    candidate = Path(str(raw_path))
    if candidate.exists():
        return str(candidate)
    local = project / "models" / "nearby_cwa_v32" / f"{key}.joblib"
    return str(local)


def _wind_speed_passed(metrics: dict[str, Any]) -> bool:
    h1 = metrics.get("wind_speed", {}).get("H1", {})
    h2 = metrics.get("wind_speed", {}).get("H2", {})
    return bool(h1.get("beats_persistence", False)) and float(h1.get("MAE", 999)) <= 1.3 and float(h2.get("MAE", 999)) <= 1.5


def _wind_gust_passed(metrics: dict[str, Any]) -> bool:
    h1 = metrics.get("wind_gust", {}).get("H1", {})
    h2 = metrics.get("wind_gust", {}).get("H2", {})
    return float(h1.get("MAE", 999)) <= 2.4 and float(h2.get("MAE", 999)) <= 2.8


def _rain_passed(metrics: dict[str, Any]) -> bool:
    h1 = metrics.get("rain_probability", {}).get("H1", {})
    return float(h1.get("Brier Score", 999)) <= 0.25 and float(h1.get("FAR", 999)) <= 0.75 and float(h1.get("POD", 0)) >= 0.30


def _training_start(project: Path) -> str | None:
    return _historical_date(project, min)


def _training_end(project: Path) -> str | None:
    return _historical_date(project, max)


def _historical_date(project: Path, reducer) -> str | None:
    hist = project / "data" / "raw" / "historical_weather"
    dates: list[str] = []
    for path in hist.glob("*.csv"):
        stem = path.stem
        parts = stem.split("_")
        for part in parts:
            if len(part) == 8 and part.isdigit():
                dates.append(f"{part[:4]}-{part[4:6]}-{part[6:]}")
    return reducer(dates) if dates else None


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _hash_json(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _empty_registry() -> dict[str, Any]:
    return {"registry_version": "v3.4", "models": {}}


def _manifest_invalid_reason(trained: bool, accepted: bool, critical: int, missing_artifacts: list[str]) -> str:
    if not trained:
        return "model_not_trained"
    if not accepted:
        return "model_not_accepted"
    if critical > 0:
        return "critical_under_warning_count_gt_0"
    if missing_artifacts:
        return "model_artifact_missing"
    return "manifest_validation_failed"
