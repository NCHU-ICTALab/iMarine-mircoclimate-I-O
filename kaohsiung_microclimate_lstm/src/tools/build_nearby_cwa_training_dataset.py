from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

try:
    from ..config import ROOT, load_config
    from ..data.historical_weather_normalizer import load_historical_weather_csv
    from ..data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from ..data.nearby_historical_training_dataset import build_nearby_historical_training_dataset
    from .rank_nearby_cwa_stations import run_rank_nearby_cwa_stations
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.historical_weather_normalizer import load_historical_weather_csv
    from data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from data.nearby_historical_training_dataset import build_nearby_historical_training_dataset
    from tools.rank_nearby_cwa_stations import run_rank_nearby_cwa_stations


def run_build_nearby_cwa_training_dataset(
    config_path: str | Path,
    historical_weather_dir: str | Path,
    output: str | Path,
    report_dir: str | Path,
    project_root: str | Path = ROOT,
) -> dict:
    project = Path(project_root)
    cfg = load_config(config_path)
    report_path = _resolve_path(report_dir, project)
    ranking = run_rank_nearby_cwa_stations(config_path, report_path, project)
    station_frames = _load_frames(_resolve_path(historical_weather_dir, project), ranking["selected_station_ids"], project)
    readiness = check_nearby_historical_training_readiness(station_frames, ranking["selected_station_ids"], cfg)
    built = build_nearby_historical_training_dataset(station_frames, ranking, cfg)
    output_path = _resolve_path(output, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    storage = _write_dataset(built["dataset"], output_path)
    report_path.mkdir(parents=True, exist_ok=True)
    dataset_report = {**built["dataset_report"], "dataset_path": str(output_path), "dataset_storage_format": storage, "readiness": readiness}
    (report_path / "nearby_cwa_readiness_report.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_path / "nearby_cwa_training_dataset_report.json").write_text(json.dumps(dataset_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dataset": built["dataset"], "readiness": readiness, "dataset_report": dataset_report}


def load_nearby_cwa_training_dataset(path: str | Path) -> pd.DataFrame:
    dataset_path = Path(path)
    try:
        return pd.read_parquet(dataset_path)
    except Exception:
        return pd.read_pickle(dataset_path)


def _load_frames(base_dir: Path, station_ids: list[str], project: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    processed = project / "data" / "processed" / "nearby_cwa_historical"
    for station_id in station_ids:
        parquet = processed / f"{station_id}.parquet"
        if parquet.exists():
            frames[station_id] = load_nearby_cwa_training_dataset(parquet)
            continue
        files = sorted((base_dir / station_id).glob("*.csv")) if (base_dir / station_id).exists() else sorted(base_dir.glob(f"{station_id}*.csv"))
        if files:
            frames[station_id] = load_historical_weather_csv(files[-1], station_id)
    return frames


def _write_dataset(dataset: pd.DataFrame, output_path: Path) -> str:
    try:
        dataset.to_parquet(output_path, index=False)
        return "parquet"
    except Exception:
        dataset.to_pickle(output_path)
        return "pickle"


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
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/data/processed/nearby_cwa_training_dataset_v32.parquet")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v32")
    args = parser.parse_args()
    result = run_build_nearby_cwa_training_dataset(args.config, args.historical_weather_dir, args.output, args.report_dir)
    print(json.dumps(result["readiness"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
