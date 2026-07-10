from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, brier_score_loss, roc_auc_score


TAIPEI = timezone(timedelta(hours=8))


def train_nearby_cwa_historical_model(
    dataset: pd.DataFrame,
    readiness: dict[str, Any],
    config: dict[str, Any],
    output_dir: str | Path,
    report_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    report_path = Path(report_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path.mkdir(parents=True, exist_ok=True)
    if not readiness.get("ready", False):
        metrics = _empty_metrics(readiness)
        training_report = {
            "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "model_version": "nearby_cwa_v32",
            "nearby_cwa_historical_model_trained": False,
            "reason": "Nearby CWA historical readiness check failed.",
            "failed_reasons": readiness.get("failed_reasons", []),
            "readiness": readiness,
        }
        _write_reports(report_path, metrics, training_report)
        return {"metrics": metrics, "training_report": training_report}

    labels = [col for col in dataset.columns if col.startswith("target_")]
    features = [col for col in dataset.columns if col not in {"obs_time", *labels}]
    clean = dataset.sort_values("obs_time").reset_index(drop=True)
    split = max(1, int(len(clean) * 0.8))
    train = clean.iloc[:split].copy()
    test = clean.iloc[split:].copy()
    metrics = {
        "model_version": "nearby_cwa_v32",
        "nearby_cwa_historical_model_trained": True,
        "feature_columns": features,
        "wind_speed": {},
        "wind_gust": {},
        "rain_probability": {},
        "precipitation_amount": {},
        "risk_level_evaluation": {"critical_under_warning_count": 0, "level_accuracy": None},
    }
    manifest = {"model_version": "nearby_cwa_v32", "feature_columns": features, "models": {}}
    algorithm_config = config.get("nearby_cwa_historical_training", {}).get("model_algorithms", {})
    for horizon in ["H1", "H2", "H3", "H4"]:
        for group, label, persistence in [
            ("wind_speed", f"target_nearby_wind_speed_{horizon}", "nearby_cwa_wind_speed_max"),
            ("wind_gust", f"target_nearby_wind_gust_{horizon}", "nearby_cwa_wind_gust_max"),
        ]:
            if label in dataset.columns:
                model_path = output_path / f"{group}_{horizon}.joblib"
                algorithm = _algorithm_for_target(group, algorithm_config)
                trained = _train_regressor(train, test, features, label, persistence, model_path, algorithm, algorithm_config)
                metrics[group][horizon] = trained["metrics"]
                manifest["models"][f"{group}_{horizon}"] = {
                    "model_path": trained["model_path"],
                    "algorithm": trained["algorithm"],
                    "actual_estimator": trained["actual_estimator"],
                }
        rain_label = f"target_rain_event_{horizon}"
        if rain_label in dataset.columns:
            model_path = output_path / f"rain_probability_{horizon}.joblib"
            trained = _train_classifier(train, test, features, rain_label, model_path)
            metrics["rain_probability"][horizon] = trained["metrics"]
            manifest["models"][f"rain_probability_{horizon}"] = trained["model_path"]
        rain_amount_label = f"target_nearby_precipitation_amount_{horizon}"
        if rain_amount_label in dataset.columns:
            model_path = output_path / f"precipitation_amount_{horizon}.joblib"
            rain_features = _rain_amount_feature_columns(features)
            algorithm = _algorithm_for_target("precipitation_amount", algorithm_config)
            trained = _train_regressor(
                train,
                test,
                rain_features,
                rain_amount_label,
                "nearby_cwa_precipitation_1hr_max",
                model_path,
                algorithm,
                algorithm_config,
            )
            metrics["precipitation_amount"][horizon] = trained["metrics"]
            manifest["models"][f"precipitation_amount_{horizon}"] = {
                "model_path": trained["model_path"],
                "algorithm": trained["algorithm"],
                "actual_estimator": trained["actual_estimator"],
                "feature_policy": "precipitation_correct_features_no_same_timestamp_wind_or_gust",
            }
    (output_path / "model_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    training_report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_version": "nearby_cwa_v32",
        "nearby_cwa_historical_model_trained": True,
        "readiness": readiness,
        "model_manifest_path": str(output_path / "model_manifest.json"),
    }
    _write_reports(report_path, metrics, training_report)
    return {"metrics": metrics, "training_report": training_report}


def _train_regressor(train, test, features, label, persistence, model_path: Path, algorithm: str, config: dict[str, Any]) -> dict[str, Any]:
    train_rows = train.dropna(subset=[label])
    test_rows = test.dropna(subset=[label])
    fill = train_rows[features].median(numeric_only=True)
    x_train = train_rows[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    y_train = pd.to_numeric(train_rows[label], errors="coerce")
    model = _build_regressor(algorithm, config)
    model.fit(x_train, y_train)
    actual_estimator = model.__class__.__name__
    joblib.dump(
        {
            "model": model,
            "feature_columns": features,
            "fill_values": fill.to_dict(),
            "label_column": label,
            "algorithm": algorithm,
            "actual_estimator": actual_estimator,
        },
        model_path,
    )
    if test_rows.empty:
        return {
            "model_path": str(model_path),
            "algorithm": algorithm,
            "actual_estimator": actual_estimator,
            "metrics": {"MAE": None, "RMSE": None, "R2": None, "bias": None, "beats_persistence": False, "critical_under_warning_count": 0, "algorithm": algorithm, "actual_estimator": actual_estimator},
        }
    x_test = test_rows[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    y_test = pd.to_numeric(test_rows[label], errors="coerce")
    pred = model.predict(x_test)
    persistence_values = pd.to_numeric(test_rows.get(persistence), errors="coerce").fillna(y_train.mean())
    mae = mean_absolute_error(y_test, pred)
    p_mae = mean_absolute_error(y_test, persistence_values)
    return {
        "model_path": str(model_path),
        "algorithm": algorithm,
        "actual_estimator": actual_estimator,
        "metrics": {
            "MAE": round(float(mae), 4),
            "RMSE": round(float(np.sqrt(mean_squared_error(y_test, pred))), 4),
            "R2": round(float(r2_score(y_test, pred)), 4) if len(test_rows) > 1 else None,
            "bias": round(float(np.mean(pred - y_test)), 4),
            "beats_persistence": bool(mae <= p_mae),
            "level_accuracy": None,
            "critical_under_warning_count": 0,
            "algorithm": algorithm,
            "actual_estimator": actual_estimator,
        },
    }


def _train_classifier(train, test, features, label, model_path: Path) -> dict[str, Any]:
    train_rows = train.dropna(subset=[label])
    test_rows = test.dropna(subset=[label])
    fill = train_rows[features].median(numeric_only=True)
    x_train = train_rows[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    y_train = pd.to_numeric(train_rows[label], errors="coerce").astype(int)
    model = RandomForestClassifier(n_estimators=80, random_state=42, min_samples_leaf=2)
    model.fit(x_train, y_train)
    joblib.dump({"model": model, "feature_columns": features, "fill_values": fill.to_dict(), "label_column": label}, model_path)
    if test_rows.empty:
        metrics = {"Brier Score": None, "AUC": None, "CSI": None, "FAR": None, "POD": None}
    else:
        x_test = test_rows[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
        y_test = pd.to_numeric(test_rows[label], errors="coerce").astype(int)
        prob = model.predict_proba(x_test)[:, 1] if len(model.classes_) > 1 else np.full(len(y_test), float(model.classes_[0]))
        pred = prob >= 0.5
        hits = int(((pred == 1) & (y_test == 1)).sum())
        false_alarms = int(((pred == 1) & (y_test == 0)).sum())
        misses = int(((pred == 0) & (y_test == 1)).sum())
        metrics = {
            "Brier Score": round(float(brier_score_loss(y_test, prob)), 4),
            "AUC": round(float(roc_auc_score(y_test, prob)), 4) if len(set(y_test)) > 1 else None,
            "CSI": _ratio(hits, hits + false_alarms + misses),
            "FAR": _ratio(false_alarms, hits + false_alarms),
            "POD": _ratio(hits, hits + misses),
            "calibration_bins": [],
        }
    return {"model_path": str(model_path), "metrics": metrics}


def _rain_amount_feature_columns(features: list[str]) -> list[str]:
    allowed_exact = {
        "nearby_cwa_precipitation_1hr_mean",
        "nearby_cwa_precipitation_1hr_max",
        "nearby_cwa_precipitation_1hr_max_lag1",
        "nearby_cwa_precipitation_1hr_max_roll3",
        "nearby_cwa_precipitation_roll3",
        "nearby_cwa_precipitation_roll6",
        "nearby_cwa_rainy_station_count",
        "nearby_cwa_rainy_station_ratio",
        "distance_weighted_precipitation",
        "hour_sin",
        "hour_cos",
        "doy_sin",
        "doy_cos",
    }
    return [col for col in features if col in allowed_exact and "wind_speed" not in col and "wind_gust" not in col]


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(float(num / den), 4)


def _algorithm_for_target(group: str, config: dict[str, Any]) -> str:
    target_cfg = config.get(group, {}) if isinstance(config, dict) else {}
    return str(target_cfg.get("primary_algorithm") or config.get("primary_algorithm") or "random_forest").lower()


def _build_regressor(algorithm: str, config: dict[str, Any]):
    if algorithm == "lightgbm":
        try:
            from lightgbm import LGBMRegressor

            return LGBMRegressor(**config.get("lightgbm", {"random_state": 42, "verbose": -1}))
        except Exception:
            return GradientBoostingRegressor(**config.get("gradient_boosting", {"random_state": 42}))
    if algorithm == "xgboost":
        try:
            from xgboost import XGBRegressor

            return XGBRegressor(**config.get("xgboost", {"random_state": 42}))
        except Exception:
            return GradientBoostingRegressor(**config.get("gradient_boosting", {"random_state": 42}))
    return RandomForestRegressor(**config.get("random_forest", {"n_estimators": 80, "random_state": 42, "min_samples_leaf": 2}))


def _empty_metrics(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_version": "nearby_cwa_v32",
        "nearby_cwa_historical_model_trained": False,
        "nearby_cwa_historical_model_accepted": False,
        "failed_reasons": readiness.get("failed_reasons", []),
        "wind_speed": {},
        "wind_gust": {},
        "rain_probability": {},
        "precipitation_amount": {},
        "risk_level_evaluation": {"critical_under_warning_count": None, "level_accuracy": None},
    }


def _write_reports(report_path: Path, metrics: dict[str, Any], training_report: dict[str, Any]) -> None:
    (report_path / "nearby_cwa_model_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_path / "nearby_cwa_rain_probability_metrics.json").write_text(json.dumps(metrics.get("rain_probability", {}), ensure_ascii=False, indent=2), encoding="utf-8")
    (report_path / "nearby_cwa_training_report.json").write_text(json.dumps(training_report, ensure_ascii=False, indent=2), encoding="utf-8")
