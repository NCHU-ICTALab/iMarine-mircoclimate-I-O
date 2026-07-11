from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    from ..config import ROOT, load_config
    from ..data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from ..data.nearby_historical_training_dataset import build_nearby_historical_training_dataset
    from ..training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from .build_nearby_cwa_training_dataset import _load_frames, _write_dataset
    from .rank_nearby_cwa_stations import run_rank_nearby_cwa_stations
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from data.nearby_historical_training_dataset import build_nearby_historical_training_dataset
    from training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from tools.build_nearby_cwa_training_dataset import _load_frames, _write_dataset
    from tools.rank_nearby_cwa_stations import run_rank_nearby_cwa_stations


def evaluate_pressure_humidity_features(
    config_path: str | Path,
    historical_weather_dir: str | Path,
    output_dir: str | Path,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    output_path = _resolve_path(output_dir, project)
    output_path.mkdir(parents=True, exist_ok=True)
    ranking = run_rank_nearby_cwa_stations(config_path, output_path / "ranking", project)
    station_frames = _load_frames(_resolve_path(historical_weather_dir, project), ranking["selected_station_ids"], project)
    readiness = check_nearby_historical_training_readiness(station_frames, ranking["selected_station_ids"], cfg)

    baseline_cfg = _with_pressure_humidity_enabled(cfg, False)
    feature_cfg = _with_pressure_humidity_enabled(cfg, True)
    baseline_dataset = build_nearby_historical_training_dataset(station_frames, ranking, baseline_cfg)["dataset"]
    feature_dataset = build_nearby_historical_training_dataset(station_frames, ranking, feature_cfg)["dataset"]
    _write_dataset(baseline_dataset, output_path / "baseline_dataset.parquet")
    _write_dataset(feature_dataset, output_path / "pressure_humidity_dataset.parquet")

    baseline_result = train_nearby_cwa_historical_model(
        baseline_dataset,
        readiness,
        baseline_cfg,
        output_path / "baseline_models",
        output_path / "baseline_reports",
    )
    feature_result = train_nearby_cwa_historical_model(
        feature_dataset,
        readiness,
        feature_cfg,
        output_path / "pressure_humidity_models",
        output_path / "pressure_humidity_reports",
    )
    feature_columns = [
        col
        for col in feature_dataset.columns
        if col.startswith(("nearby_cwa_pressure", "nearby_cwa_relative_humidity", "nearby_cwa_temperature", "nearby_cwa_dew_point"))
    ]
    report = {
        "evaluated": True,
        "evaluation_mode": "full_scale_production_config",
        "sample_count": int(len(feature_dataset)),
        "readiness": readiness,
        "pressure_humidity_feature_columns": feature_columns,
        "comparison": _compare_metrics(baseline_result["metrics"], feature_result["metrics"]),
        "baseline_metrics_path": str(output_path / "baseline_reports" / "nearby_cwa_model_metrics.json"),
        "pressure_humidity_metrics_path": str(output_path / "pressure_humidity_reports" / "nearby_cwa_model_metrics.json"),
    }
    (output_path / "comparison_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _with_pressure_humidity_enabled(config: dict[str, Any], enabled: bool) -> dict[str, Any]:
    cfg = copy.deepcopy(config)
    training = cfg.setdefault("nearby_cwa_historical_training", {})
    training["enable_pressure_humidity_features"] = bool(enabled)
    return cfg


def _compare_metrics(baseline: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for group in ["wind_speed", "wind_gust", "rain_probability", "precipitation_amount"]:
        comparison[group] = {}
        for horizon in ["H1", "H2", "H3", "H4"]:
            base_metrics = baseline.get(group, {}).get(horizon, {})
            feature_metrics = feature.get(group, {}).get(horizon, {})
            comparison[group][horizon] = {
                "baseline": _pick(base_metrics),
                "with_pressure_humidity_features": _pick(feature_metrics),
                "delta_MAE": _delta(feature_metrics.get("MAE"), base_metrics.get("MAE")),
                "delta_R2": _delta(feature_metrics.get("R2"), base_metrics.get("R2")),
                "delta_AUC": _delta(feature_metrics.get("AUC"), base_metrics.get("AUC")),
                "delta_CSI": _delta(feature_metrics.get("CSI"), base_metrics.get("CSI")),
                "improved_by_primary_metric": _improved(group, base_metrics, feature_metrics),
            }
    return comparison


def _pick(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ["MAE", "RMSE", "R2", "bias", "beats_persistence", "Brier Score", "AUC", "CSI", "FAR", "POD", "algorithm", "actual_estimator"]
    return {key: metrics.get(key) for key in keys if key in metrics}


def _delta(new_value: Any, old_value: Any) -> float | None:
    if new_value is None or old_value is None:
        return None
    return round(float(new_value) - float(old_value), 4)


def _improved(group: str, baseline: dict[str, Any], feature: dict[str, Any]) -> bool | None:
    if group == "rain_probability":
        old = baseline.get("AUC")
        new = feature.get("AUC")
        if old is None or new is None:
            return None
        return bool(float(new) > float(old))
    old = baseline.get("MAE")
    new = feature.get("MAE")
    if old is None or new is None:
        return None
    return bool(float(new) < float(old))


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
    parser.add_argument("--historical-weather-dir", default="kaohsiung_microclimate_lstm/data/raw/historical_weather")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/results/model_benchmark_v13/pressure_humidity_features")
    args = parser.parse_args()
    report = evaluate_pressure_humidity_features(args.config, args.historical_weather_dir, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
