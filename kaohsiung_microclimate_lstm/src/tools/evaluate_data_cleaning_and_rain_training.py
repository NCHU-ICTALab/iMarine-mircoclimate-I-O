from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
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


TAIPEI = timezone(timedelta(hours=8))
KNOWN_POLLUTED_BASELINE = {
    "wind_speed": {"H1": {"R2": 0.3698}},
    "wind_gust": {"H1": {"R2": 0.8519}},
    "precipitation_amount": {"H1": {"R2": -0.1054}},
}


def evaluate_data_cleaning_and_rain_training(
    config_path: str | Path,
    historical_weather_dir: str | Path,
    output_dir: str | Path,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    out = _resolve_path(output_dir, project)
    out.mkdir(parents=True, exist_ok=True)
    ranking = run_rank_nearby_cwa_stations(config_path, out / "ranking", project)
    station_frames = _load_frames(_resolve_path(historical_weather_dir, project), ranking["selected_station_ids"], project)
    readiness = check_nearby_historical_training_readiness(station_frames, ranking["selected_station_ids"], cfg)

    stage1 = _run_stage("stage1_clean_data", cfg, station_frames, ranking, readiness, out)
    stage2_cfg = _rain_training_config(cfg, train_on_rain_events_only=True, log1p_target=False)
    stage2 = _run_stage("stage2_rain_event_only", stage2_cfg, station_frames, ranking, readiness, out)
    stage2_improved = _precipitation_improved(stage1["metrics"], stage2["metrics"])
    stage3_base_cfg = stage2_cfg if stage2_improved else cfg
    stage3_cfg = _rain_training_config(stage3_base_cfg, log1p_target=True)
    stage3_name = "stage3_log1p_after_stage2" if stage2_improved else "stage3_log1p_after_stage1"
    stage3 = _run_stage(stage3_name, stage3_cfg, station_frames, ranking, readiness, out)

    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "evaluation_mode": "full_scale_production_config",
        "known_polluted_baseline": KNOWN_POLLUTED_BASELINE,
        "readiness": readiness,
        "stage2_stacked_into_stage3": bool(stage2_improved),
        "stages": {
            "stage1_clean_data": _stage_summary(stage1, None),
            "stage2_rain_event_only": _stage_summary(stage2, stage1["metrics"]),
            stage3_name: _stage_summary(stage3, stage2["metrics"] if stage2_improved else stage1["metrics"]),
        },
    }
    (out / "comparison_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _run_stage(name: str, cfg: dict[str, Any], station_frames: dict[str, Any], ranking: dict[str, Any], readiness: dict[str, Any], out: Path) -> dict[str, Any]:
    built = build_nearby_historical_training_dataset(station_frames, ranking, cfg)
    stage_dir = out / name
    stage_dir.mkdir(parents=True, exist_ok=True)
    _write_dataset(built["dataset"], stage_dir / "dataset.parquet")
    result = train_nearby_cwa_historical_model(built["dataset"], readiness, cfg, stage_dir / "models", stage_dir / "reports")
    stage_report = {
        "stage": name,
        "dataset_report": built["dataset_report"],
        "metrics": result["metrics"],
        "training_report": result["training_report"],
    }
    (out / f"{name}_metrics.json").write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return stage_report


def _rain_training_config(config: dict[str, Any], train_on_rain_events_only: bool | None = None, log1p_target: bool | None = None) -> dict[str, Any]:
    cfg = copy.deepcopy(config)
    rain_cfg = cfg.setdefault("nearby_cwa_historical_training", {}).setdefault("precipitation_amount_training", {})
    if train_on_rain_events_only is not None:
        rain_cfg["train_on_rain_events_only"] = bool(train_on_rain_events_only)
    if log1p_target is not None:
        rain_cfg["log1p_target"] = bool(log1p_target)
    return cfg


def _precipitation_improved(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    prev_h1 = previous.get("precipitation_amount", {}).get("H1", {})
    curr_h1 = current.get("precipitation_amount", {}).get("H1", {})
    if prev_h1.get("MAE") is None or curr_h1.get("MAE") is None:
        return False
    return float(curr_h1["MAE"]) < float(prev_h1["MAE"])


def _stage_summary(stage: dict[str, Any], previous_metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = stage["metrics"]
    summary = {
        "dataset_sample_count": stage["dataset_report"].get("sample_count"),
        "metrics_path": stage["training_report"].get("model_manifest_path"),
        "targets": {},
    }
    for group in ["wind_speed", "wind_gust", "rain_probability", "precipitation_amount"]:
        summary["targets"][group] = {}
        for horizon in ["H1", "H2", "H3", "H4"]:
            current = metrics.get(group, {}).get(horizon, {})
            previous = previous_metrics.get(group, {}).get(horizon, {}) if previous_metrics else {}
            summary["targets"][group][horizon] = {
                "current": _pick(current),
                "delta_vs_previous": _delta_metrics(current, previous),
            }
    return summary


def _pick(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ["MAE", "RMSE", "R2", "bias", "beats_persistence", "Brier Score", "AUC", "CSI", "FAR", "POD", "sample_filter_column", "target_transform"]
    return {key: metrics.get(key) for key in keys if key in metrics}


def _delta_metrics(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, float | None]:
    return {f"delta_{key}": _delta(current.get(key), previous.get(key)) for key in ["MAE", "RMSE", "R2", "AUC", "CSI"]}


def _delta(new_value: Any, old_value: Any) -> float | None:
    if new_value is None or old_value is None:
        return None
    return round(float(new_value) - float(old_value), 4)


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
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/results/model_benchmark_v13/data_cleaning_and_rain_training")
    args = parser.parse_args()
    report = evaluate_data_cleaning_and_rain_training(args.config, args.historical_weather_dir, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
