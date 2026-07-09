from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from ..config import ROOT, load_config
    from ..data.dataset_readiness import check_port_local_dataset_readiness
    from ..data.port_local_training_dataset import build_port_local_training_dataset
    from ..preprocess import load_observations
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.dataset_readiness import check_port_local_dataset_readiness
    from data.port_local_training_dataset import build_port_local_training_dataset
    from preprocess import load_observations


TAIPEI = timezone(timedelta(hours=8))


def run_build_port_local_training_dataset(
    config_path: str | Path = "config.yaml",
    input_dir: str | Path | None = None,
    output: str | Path | None = None,
    report_dir: str | Path | None = None,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    input_path = _resolve_path(input_dir or "data/raw/observed_hourly", project)
    output_path = _resolve_path(output or cfg.get("port_local_training", {}).get("dataset_output", "data/processed/port_local_training_dataset.parquet"), project)
    report_path = _resolve_path(report_dir or "results/dispatch_risk_v30", project)
    frames = _load_khwd_frames(input_path)
    built = build_port_local_training_dataset(frames, {"train_rain": bool(cfg.get("port_local_model", {}).get("train_rain_probability_if_labels_available", True))}, cfg)
    dataset: pd.DataFrame = built["dataset"]
    readiness = check_port_local_dataset_readiness(dataset, cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    storage_format = _write_dataset(dataset, output_path)
    report_path.mkdir(parents=True, exist_ok=True)
    dataset_report = {
        **built["dataset_report"],
        "dataset_path": str(output_path),
        "dataset_storage_format": storage_format,
        "khwd_station_files_loaded": sorted(frames),
        "readiness": readiness,
    }
    readiness_report = {"generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"), **readiness}
    (report_path / "dataset_readiness_report.json").write_text(json.dumps(readiness_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_path / "port_local_training_dataset_report.json").write_text(json.dumps(dataset_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dataset": dataset, "dataset_report": dataset_report, "readiness_report": readiness_report}


def load_port_local_training_dataset(path: str | Path) -> pd.DataFrame:
    dataset_path = Path(path)
    try:
        return pd.read_parquet(dataset_path)
    except Exception:
        return pd.read_pickle(dataset_path)


def _load_khwd_frames(input_path: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(input_path.glob("KHWD*.csv")):
        try:
            frames[path.stem] = load_observations(path)
        except Exception:
            try:
                frames[path.stem] = pd.read_csv(path)
            except Exception:
                continue
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
    parser = argparse.ArgumentParser(description="Build KHWD port-local supervised training dataset.")
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--input-dir", default="kaohsiung_microclimate_lstm/data/raw/observed_hourly")
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/data/processed/port_local_training_dataset.parquet")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v30")
    args = parser.parse_args()
    project = ROOT
    result = run_build_port_local_training_dataset(
        config_path=args.config,
        input_dir=args.input_dir,
        output=args.output,
        report_dir=args.report_dir,
        project_root=project,
    )
    print(json.dumps(result["readiness_report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
