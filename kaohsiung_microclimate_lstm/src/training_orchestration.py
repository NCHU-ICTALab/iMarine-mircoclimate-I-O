from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import ROOT, load_config
from .model_registry import (
    MODEL_VERSION,
    build_model_registry_summary,
    ensure_v34_registry_and_manifest,
)


TAIPEI = timezone(timedelta(hours=8))


def run_training_orchestration(
    config_path: str | Path = "kaohsiung_microclimate_lstm/config.yaml",
    target_area: str = "KHH",
    report_dir: str | Path | None = None,
    project_root: str | Path = ROOT,
    force_train: bool = False,
    dry_run: bool = False,
    simulate_missing_manifest: bool = False,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    out_dir = _resolve_report_dir(report_dir or cfg.get("training_orchestration", {}).get("report_dir", "results/dispatch_risk_v34"), project)
    registry_bundle = ensure_v34_registry_and_manifest(project, cfg, target_area)
    nearby_validation = dict(registry_bundle["nearby_manifest_validation"])
    if simulate_missing_manifest:
        nearby_validation.update({"valid": False, "trained": False, "accepted": False, "reason": "simulated_missing_manifest", "manifest": {}})

    nearby_model = registry_bundle["registry"].get("models", {}).get("nearby_cwa_historical_model", {})
    if simulate_missing_manifest:
        nearby_model = {**nearby_model, "trained": False, "available": False, "accepted": False, "reason": "simulated_missing_manifest"}

    if force_train:
        training_required = True
        training_skipped = False
        reason = "force_train requested; training pipeline should rebuild dataset, train, evaluate, and update manifest."
    elif dry_run and not nearby_validation.get("valid", False):
        training_required = True
        training_skipped = False
        reason = "Dry run: no accepted nearby CWA historical model manifest found."
    elif nearby_validation.get("valid", False):
        training_required = False
        training_skipped = True
        reason = "Existing accepted nearby CWA historical model found."
    else:
        training_required = True
        training_skipped = False
        reason = "No accepted nearby CWA historical model manifest found."

    report = {
        "model_version": cfg.get("project", {}).get("model_version", MODEL_VERSION),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "training_orchestration_version": "v3.4",
        "target_area": target_area,
        "training_checked": True,
        "training_required": training_required,
        "training_skipped": training_skipped,
        "skip_reason": reason if training_skipped else None,
        "training_reason": None if training_skipped else reason,
        "dry_run": bool(dry_run),
        "force_train": bool(force_train),
        "models": {
            "port_local_model": registry_bundle["registry"].get("models", {}).get("port_local_model", {}),
            "nearby_cwa_historical_model": nearby_model,
        },
        "registry_path": registry_bundle["registry_path"],
        "nearby_manifest_path": registry_bundle["nearby_manifest_path"],
        "model_registry_summary": build_model_registry_summary(registry_bundle["registry"]),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_reports(out_dir, report, registry_bundle, nearby_validation)
    return report


def build_model_training_status(orchestration_report: dict[str, Any]) -> dict[str, Any]:
    nearby = orchestration_report.get("models", {}).get("nearby_cwa_historical_model", {})
    port = orchestration_report.get("models", {}).get("port_local_model", {})
    return {
        "training_checked": bool(orchestration_report.get("training_checked", False)),
        "training_required": bool(orchestration_report.get("training_required", False)),
        "training_skipped": bool(orchestration_report.get("training_skipped", False)),
        "skip_reason": orchestration_report.get("skip_reason"),
        "training_reason": orchestration_report.get("training_reason"),
        "last_training_run_at": orchestration_report.get("generated_at"),
        "available_models": {
            "port_local_model": {
                "trained": bool(port.get("trained", False)),
                "available": bool(port.get("available", False)),
                "accepted": bool(port.get("accepted", False)),
                "reason": port.get("reason"),
            },
            "nearby_cwa_historical_model": {
                "trained": bool(nearby.get("trained", False)),
                "available": bool(nearby.get("available", False)),
                "accepted": bool(nearby.get("accepted", False)),
                "artifact_version": nearby.get("artifact_version", "nearby_cwa_v34"),
                "selected_station_ids": nearby.get("selected_station_ids", []),
                "manifest_path": nearby.get("manifest_path"),
                "reason": nearby.get("reason"),
            },
        },
    }


def _write_reports(out_dir: Path, report: dict[str, Any], registry_bundle: dict[str, Any], nearby_validation: dict[str, Any]) -> None:
    (out_dir / "training_orchestration_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "model_registry_report.json").write_text(json.dumps(registry_bundle["registry"], ensure_ascii=False, indent=2), encoding="utf-8")
    validation_report = {
        "model_version": report["model_version"],
        "generated_at": report["generated_at"],
        "manifest_path": registry_bundle["nearby_manifest_path"],
        "valid": bool(nearby_validation.get("valid", False)),
        "trained": bool(nearby_validation.get("trained", False)),
        "accepted": bool(nearby_validation.get("accepted", False)),
        "critical_under_warning_count": int(nearby_validation.get("critical_under_warning_count", 0) or 0),
        "missing_artifacts": nearby_validation.get("missing_artifacts", []),
        "reason": nearby_validation.get("reason"),
    }
    (out_dir / "model_manifest_validation_report.json").write_text(json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_report_dir(path: str | Path, project: Path) -> Path:
    out = Path(path)
    if out.is_absolute():
        return out
    if out.parts and out.parts[0] == project.name:
        return Path.cwd() / out
    return project / out
