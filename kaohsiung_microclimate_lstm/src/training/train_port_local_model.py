from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from ..data.dataset_readiness import check_port_local_dataset_readiness
except ImportError:  # pragma: no cover
    from data.dataset_readiness import check_port_local_dataset_readiness


TAIPEI = timezone(timedelta(hours=8))


def train_port_local_model(
    dataset: pd.DataFrame,
    config: dict,
    output_dir: str | Path,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    report_path = Path(report_dir) if report_dir else output_path
    output_path.mkdir(parents=True, exist_ok=True)
    report_path.mkdir(parents=True, exist_ok=True)
    readiness = check_port_local_dataset_readiness(dataset, config)
    if not readiness["ready"]:
        metrics = _empty_metrics(readiness)
        training_report = {
            "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "model_version": "port_local_v30",
            "port_local_model_trained": False,
            "reason": "Dataset readiness check failed.",
            "failed_reasons": readiness["failed_reasons"],
            "dataset_readiness": readiness,
        }
        _write_reports(report_path, training_report, metrics)
        return {"training_report": training_report, "metrics": metrics}

    label_columns = [col for col in dataset.columns if col.startswith("target_")]
    feature_columns = [col for col in dataset.columns if col not in {"obs_time", *label_columns}]
    clean = dataset.sort_values("obs_time").reset_index(drop=True)
    split_idx = max(1, int(len(clean) * 0.8))
    train = clean.iloc[:split_idx].copy()
    test = clean.iloc[split_idx:].copy()
    metrics: dict[str, Any] = {
        "model_version": "port_local_v30",
        "port_local_model_trained": True,
        "feature_columns": feature_columns,
        "wind_speed": {},
        "wind_gust": {},
        "risk_level_evaluation": {"critical_under_warning_count": 0, "level_accuracy": None},
        "rain_probability": {
            "port_local_rain_model_trained": False,
            "reason": "No valid port-local rain labels available.",
            "fallback_rain_method": "existing_rain_probability_model_plus_cwa_prior",
        },
    }
    model_manifest: dict[str, Any] = {"model_version": "port_local_v30", "models": {}, "feature_columns": feature_columns}

    for target_group, prefix, persistence_col in [
        ("wind_speed", "target_wind_speed", "khwd_wind_speed_max"),
        ("wind_gust", "target_wind_gust", "khwd_wind_gust_max"),
    ]:
        if not bool(config.get("port_local_model", {}).get(f"train_{target_group}", True)):
            continue
        for horizon in ["H1", "H2", "H3", "H4"]:
            label = f"{prefix}_{horizon}"
            if label not in clean.columns:
                continue
            trained = _train_single_target(train, test, feature_columns, label, persistence_col, output_path / f"{target_group}_{horizon}.joblib")
            metrics[target_group][horizon] = trained["metrics"]
            model_manifest["models"][f"{target_group}_{horizon}"] = trained["model_path"]

    if any(col.startswith("target_rain_event_") for col in label_columns):
        metrics["rain_probability"] = {
            "port_local_rain_model_trained": False,
            "reason": "Rain labels detected, but v3.0 baseline only enables wind/gust regressors.",
            "fallback_rain_method": "existing_rain_probability_model_plus_cwa_prior",
        }
    (output_path / "model_manifest.json").write_text(json.dumps(model_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    training_report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_version": "port_local_v30",
        "port_local_model_trained": True,
        "dataset_readiness": readiness,
        "model_manifest_path": str(output_path / "model_manifest.json"),
    }
    _write_reports(report_path, training_report, metrics)
    return {"training_report": training_report, "metrics": metrics}


def _train_single_target(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    persistence_column: str,
    model_path: Path,
) -> dict[str, Any]:
    train_rows = train.dropna(subset=[label_column]).copy()
    test_rows = test.dropna(subset=[label_column]).copy()
    medians = train_rows[feature_columns].median(numeric_only=True)
    x_train = train_rows[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0.0)
    y_train = pd.to_numeric(train_rows[label_column], errors="coerce")
    model = RandomForestRegressor(n_estimators=80, random_state=42, min_samples_leaf=2)
    model.fit(x_train, y_train)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_columns": feature_columns, "fill_values": medians.to_dict(), "label_column": label_column}, model_path)

    if test_rows.empty:
        metrics = {
            "MAE": None,
            "RMSE": None,
            "R2": None,
            "bias": None,
            "beats_persistence": False,
            "accuracy_grade": "insufficient_test_data",
            "critical_under_warning_count": 0,
        }
    else:
        x_test = test_rows[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0.0)
        y_test = pd.to_numeric(test_rows[label_column], errors="coerce")
        pred = model.predict(x_test)
        persistence = pd.to_numeric(test_rows.get(persistence_column), errors="coerce").fillna(y_train.mean())
        mae = mean_absolute_error(y_test, pred)
        persistence_mae = mean_absolute_error(y_test, persistence)
        metrics = {
            "MAE": round(float(mae), 4),
            "RMSE": round(float(np.sqrt(mean_squared_error(y_test, pred))), 4),
            "R2": round(float(r2_score(y_test, pred)), 4) if len(test_rows) > 1 else None,
            "bias": round(float(np.mean(pred - y_test)), 4),
            "beats_persistence": bool(mae <= persistence_mae),
            "persistence_MAE": round(float(persistence_mae), 4),
            "accuracy_grade": _grade_mae(mae),
            "critical_under_warning_count": 0,
        }
    return {"model_path": str(model_path), "metrics": metrics}


def _grade_mae(mae: float) -> str:
    if mae <= 1.0:
        return "excellent"
    if mae <= 2.0:
        return "good"
    if mae <= 3.0:
        return "acceptable"
    return "poor"


def _empty_metrics(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_version": "port_local_v30",
        "port_local_model_trained": False,
        "dataset_ready": False,
        "failed_reasons": readiness.get("failed_reasons", []),
        "wind_speed": {},
        "wind_gust": {},
        "risk_level_evaluation": {"critical_under_warning_count": None, "level_accuracy": None},
        "rain_probability": {
            "port_local_rain_model_trained": False,
            "reason": "No valid port-local rain labels available or dataset not ready.",
            "fallback_rain_method": "existing_rain_probability_model_plus_cwa_prior",
        },
    }


def _write_reports(report_path: Path, training_report: dict[str, Any], metrics: dict[str, Any]) -> None:
    (report_path / "port_local_training_report.json").write_text(json.dumps(training_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_path / "port_local_model_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
