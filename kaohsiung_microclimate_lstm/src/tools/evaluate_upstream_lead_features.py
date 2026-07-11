from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from ..config import ROOT, load_config
    from ..training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from .build_nearby_cwa_training_dataset import load_nearby_cwa_training_dataset
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from tools.build_nearby_cwa_training_dataset import load_nearby_cwa_training_dataset


def evaluate_upstream_lead_features(
    config_path: str | Path,
    dataset_path: str | Path,
    output_dir: str | Path,
    project_root: str | Path = ROOT,
    max_rows: int | None = 20000,
    fast_estimators: int = 30,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    dataset = load_nearby_cwa_training_dataset(_resolve_path(dataset_path, project))
    if max_rows and len(dataset) > max_rows:
        dataset = dataset.sort_values("obs_time").tail(int(max_rows)).reset_index(drop=True)
    cfg = _fast_training_config(cfg, fast_estimators)
    upstream_columns = [col for col in dataset.columns if col.startswith("upstream_subset_")]
    output_path = _resolve_path(output_dir, project)
    output_path.mkdir(parents=True, exist_ok=True)
    readiness = {"ready": True, "failed_reasons": [], "selected_station_ids": []}
    if not upstream_columns:
        report = {
            "evaluated": False,
            "reason": "dataset_has_no_upstream_subset_columns",
            "upstream_feature_columns": [],
        }
        _write_report(output_path, report)
        return report

    baseline = dataset.drop(columns=upstream_columns)
    baseline_result = train_nearby_cwa_historical_model(
        baseline,
        readiness,
        cfg,
        output_path / "baseline_models",
        output_path / "baseline_reports",
    )
    upstream_result = train_nearby_cwa_historical_model(
        dataset,
        readiness,
        cfg,
        output_path / "upstream_models",
        output_path / "upstream_reports",
    )
    report = {
        "evaluated": True,
        "evaluation_mode": "recent_tail_sample_fast_random_forest",
        "sample_count": int(len(dataset)),
        "max_rows": max_rows,
        "fast_estimators": int(fast_estimators),
        "upstream_feature_columns": upstream_columns,
        "comparison": _compare_metrics(baseline_result["metrics"], upstream_result["metrics"]),
        "baseline_metrics_path": str(output_path / "baseline_reports" / "nearby_cwa_model_metrics.json"),
        "upstream_metrics_path": str(output_path / "upstream_reports" / "nearby_cwa_model_metrics.json"),
    }
    _write_report(output_path, report)
    return report


def _write_report(output_path: Path, report: dict[str, Any]) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (output_path / "comparison_report.json").write_text(text, encoding="utf-8")
    (output_path / "upstream_lead_feature_evaluation.json").write_text(text, encoding="utf-8")


def _fast_training_config(config: dict[str, Any], fast_estimators: int) -> dict[str, Any]:
    cfg = dict(config)
    training = dict(cfg.get("nearby_cwa_historical_training", {}))
    algorithms = dict(training.get("model_algorithms", {}))
    algorithms["primary_algorithm"] = "random_forest"
    algorithms["wind_speed"] = {"primary_algorithm": "random_forest"}
    algorithms["wind_gust"] = {"primary_algorithm": "random_forest"}
    algorithms["precipitation_amount"] = {"primary_algorithm": "random_forest"}
    algorithms["random_forest"] = {"n_estimators": int(fast_estimators), "random_state": 42, "min_samples_leaf": 2, "n_jobs": -1}
    training["model_algorithms"] = algorithms
    cfg["nearby_cwa_historical_training"] = training
    return cfg


def _compare_metrics(baseline: dict[str, Any], upstream: dict[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for group in ["wind_speed", "wind_gust", "precipitation_amount"]:
        comparison[group] = {}
        for horizon in ["H1", "H2", "H3", "H4"]:
            base_metrics = baseline.get(group, {}).get(horizon, {})
            up_metrics = upstream.get(group, {}).get(horizon, {})
            comparison[group][horizon] = {
                "baseline": _pick(base_metrics),
                "with_upstream_features": _pick(up_metrics),
                "delta_MAE": _delta(up_metrics.get("MAE"), base_metrics.get("MAE")),
                "delta_R2": _delta(up_metrics.get("R2"), base_metrics.get("R2")),
                "improved_by_MAE": _improved_mae(base_metrics.get("MAE"), up_metrics.get("MAE")),
            }
    return comparison


def _pick(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics.get(key) for key in ["MAE", "RMSE", "R2", "bias", "beats_persistence", "algorithm", "actual_estimator"]}


def _delta(new_value: Any, old_value: Any) -> float | None:
    if new_value is None or old_value is None:
        return None
    return round(float(new_value) - float(old_value), 4)


def _improved_mae(old_value: Any, new_value: Any) -> bool | None:
    if old_value is None or new_value is None:
        return None
    return bool(float(new_value) < float(old_value))


def _resolve_path(path: str | Path, project: Path) -> Path:
    out = Path(path)
    if out.is_absolute() or out.exists():
        return out
    if out.parts and out.parts[0] == project.name:
        return Path.cwd() / out
    return project / out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--dataset", default="kaohsiung_microclimate_lstm/data/processed/nearby_cwa_training_dataset_v32.parquet")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/results/model_benchmark_v13/upstream_lead_features")
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument("--fast-estimators", type=int, default=30)
    args = parser.parse_args()
    report = evaluate_upstream_lead_features(args.config, args.dataset, args.output_dir, max_rows=args.max_rows, fast_estimators=args.fast_estimators)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
