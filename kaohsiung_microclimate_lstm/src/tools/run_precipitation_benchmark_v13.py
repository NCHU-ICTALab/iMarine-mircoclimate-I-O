from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error, precision_score, recall_score, r2_score, roc_auc_score

try:
    from ..config import ROOT, load_config
except ImportError:  # pragma: no cover
    from config import ROOT, load_config


TAIPEI = timezone(timedelta(hours=8))
RAIN_FEATURE_KEYWORDS = ("precipitation", "rainy", "rain", "hour_", "doy_", "station_count")


def run_precipitation_benchmark_v13(
    dataset_path: str | Path,
    output_dir: str | Path,
    config_path: str | Path | None = ROOT / "config.yaml",
    algorithms: list[str] | None = None,
    horizons: list[str] | None = None,
) -> dict[str, Any]:
    dataset = _read_dataset(Path(dataset_path)).sort_values("obs_time").reset_index(drop=True)
    config = load_config(config_path) if config_path else {}
    selected_algorithms = algorithms or config.get("model_benchmark", {}).get("candidate_algorithms") or ["random_forest", "lightgbm", "xgboost"]
    selected_horizons = horizons or ["H1", "H2", "H3", "H4"]
    label_columns = [col for col in dataset.columns if col.startswith("target_")]
    features = [
        col
        for col in dataset.columns
        if col not in {"obs_time", *label_columns}
        and any(keyword in col for keyword in RAIN_FEATURE_KEYWORDS)
        and "wind_speed" not in col
        and "wind_gust" not in col
    ]
    if not features:
        raise ValueError("No non-leaking rain lag/rolling feature columns found.")

    report: dict[str, Any] = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "benchmark_version": "precipitation_v13_no_leakage",
        "leakage_policy": "uses rain/time/station-count features only; excludes same-timestamp wind_speed/wind_gust cross-target features",
        "feature_columns": features,
        "algorithms": selected_algorithms,
        "horizons": {},
    }
    for horizon in selected_horizons:
        event_label = f"target_rain_event_{horizon}"
        amount_label = f"target_nearby_precipitation_1hr_{horizon}"
        if event_label not in dataset.columns or amount_label not in dataset.columns:
            report["horizons"][horizon] = {"skipped": True, "reason": "required event or amount label missing"}
            continue
        report["horizons"][horizon] = _benchmark_horizon(dataset, features, event_label, amount_label, selected_algorithms)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "precipitation_benchmark_v13.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def _benchmark_horizon(dataset: pd.DataFrame, features: list[str], event_label: str, amount_label: str, algorithms: list[str]) -> dict[str, Any]:
    work = dataset[["obs_time", *features, event_label, amount_label]].dropna(subset=[event_label, amount_label]).copy()
    split = max(1, min(len(work) - 1, int(len(work) * 0.8)))
    train = work.iloc[:split]
    test = work.iloc[split:]
    fill = train[features].apply(pd.to_numeric, errors="coerce").median(numeric_only=True)
    x_train = train[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    x_test = test[features].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    y_event_train = pd.to_numeric(train[event_label], errors="coerce").astype(int)
    y_event_test = pd.to_numeric(test[event_label], errors="coerce").astype(int)
    y_amount_train = pd.to_numeric(train[amount_label], errors="coerce").astype(float)
    y_amount_test = pd.to_numeric(test[amount_label], errors="coerce").astype(float)
    results = {}
    for algorithm in algorithms:
        clf = _build_classifier(str(algorithm))
        reg = _build_regressor(str(algorithm))
        clf.fit(x_train, y_event_train)
        rainy_train = y_amount_train > 0.5
        reg.fit(x_train.loc[rainy_train], y_amount_train.loc[rainy_train] if rainy_train.any() else y_amount_train)
        probability = _predict_probability(clf, x_test)
        event_pred = probability >= 0.5
        amount_when_rain = np.asarray(reg.predict(x_test), dtype=float)
        amount_pred = np.where(event_pred, np.maximum(amount_when_rain, 0.0), 0.0)
        results[str(algorithm)] = {
            "requested_algorithm": str(algorithm),
            "actual_classifier": clf.__class__.__name__,
            "actual_regressor": reg.__class__.__name__,
            "event_metrics": _event_metrics(y_event_test, probability, event_pred),
            "amount_metrics": _amount_metrics(y_amount_test, amount_pred),
        }
    return {
        "rows_total": int(len(work)),
        "rows_train": int(len(train)),
        "rows_test": int(len(test)),
        "rain_event_rate_test": float(y_event_test.mean()) if len(y_event_test) else None,
        "results": results,
    }


def _build_classifier(algorithm: str):
    if algorithm == "lightgbm":
        try:
            from lightgbm import LGBMClassifier

            return LGBMClassifier(n_estimators=120, learning_rate=0.05, random_state=42, verbose=-1)
        except Exception:
            return GradientBoostingClassifier(random_state=42)
    if algorithm == "xgboost":
        try:
            from xgboost import XGBClassifier

            return XGBClassifier(n_estimators=120, learning_rate=0.05, random_state=42, eval_metric="logloss")
        except Exception:
            return GradientBoostingClassifier(random_state=42)
    return RandomForestClassifier(n_estimators=80, random_state=42, min_samples_leaf=2, n_jobs=-1)


def _build_regressor(algorithm: str):
    if algorithm == "lightgbm":
        try:
            from lightgbm import LGBMRegressor

            return LGBMRegressor(n_estimators=120, learning_rate=0.05, random_state=42, verbose=-1)
        except Exception:
            return GradientBoostingRegressor(random_state=42)
    if algorithm == "xgboost":
        try:
            from xgboost import XGBRegressor

            return XGBRegressor(n_estimators=120, learning_rate=0.05, random_state=42)
        except Exception:
            return GradientBoostingRegressor(random_state=42)
    return RandomForestRegressor(n_estimators=80, random_state=42, min_samples_leaf=2, n_jobs=-1)


def _predict_probability(model: Any, x_test: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x_test)
        return proba[:, 1] if proba.shape[1] > 1 else np.full(len(x_test), float(model.classes_[0]))
    return np.asarray(model.predict(x_test), dtype=float)


def _event_metrics(y_true: pd.Series, probability: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    hits = int(((pred == 1) & (y_true == 1)).sum())
    false_alarms = int(((pred == 1) & (y_true == 0)).sum())
    misses = int(((pred == 0) & (y_true == 1)).sum())
    return {
        "Brier Score": round(float(brier_score_loss(y_true, probability)), 4),
        "AUC": round(float(roc_auc_score(y_true, probability)), 4) if len(set(y_true)) > 1 else None,
        "CSI": _ratio(hits, hits + false_alarms + misses),
        "FAR": _ratio(false_alarms, hits + false_alarms),
        "POD": _ratio(hits, hits + misses),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
    }


def _amount_metrics(y_true: pd.Series, pred: np.ndarray) -> dict[str, Any]:
    return {
        "MAE": round(float(mean_absolute_error(y_true, pred)), 4),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_true, pred))), 4),
        "R2": round(float(r2_score(y_true, pred)), 4) if len(y_true) > 1 else None,
        "bias": round(float(np.mean(pred - y_true)), 4),
    }


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(float(num / den), 4)


def _read_dataset(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.read_pickle(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="kaohsiung_microclimate_lstm/data/processed/nearby_cwa_training_dataset_v32.parquet")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/results/model_benchmark_v13/precipitation_correct_features")
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--algorithms", default=None)
    parser.add_argument("--horizons", default=None)
    args = parser.parse_args()
    algorithms = [item.strip() for item in args.algorithms.split(",") if item.strip()] if args.algorithms else None
    horizons = [item.strip() for item in args.horizons.split(",") if item.strip()] if args.horizons else None
    report = run_precipitation_benchmark_v13(args.dataset, args.output_dir, args.config, algorithms, horizons)
    print(json.dumps({"report_path": report["report_path"], "horizons": list(report["horizons"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
