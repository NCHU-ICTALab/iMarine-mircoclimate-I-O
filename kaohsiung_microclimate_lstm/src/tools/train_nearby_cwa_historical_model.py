from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ..config import ROOT, load_config
    from ..data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from ..training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from .build_nearby_cwa_training_dataset import load_nearby_cwa_training_dataset
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.nearby_historical_readiness import check_nearby_historical_training_readiness
    from training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model
    from tools.build_nearby_cwa_training_dataset import load_nearby_cwa_training_dataset


def run_train_nearby_cwa_historical_model(
    config_path: str | Path,
    dataset_path: str | Path,
    output_dir: str | Path,
    report_dir: str | Path,
    project_root: str | Path = ROOT,
) -> dict:
    project = Path(project_root)
    cfg = load_config(config_path)
    dataset = load_nearby_cwa_training_dataset(_resolve_path(dataset_path, project))
    station_frames = {sid: frame for sid, frame in dataset.groupby("station_id")} if "station_id" in dataset.columns else {}
    readiness_path = _resolve_path(report_dir, project) / "nearby_cwa_readiness_report.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8")) if readiness_path.exists() else check_nearby_historical_training_readiness(station_frames, [], cfg)
    return train_nearby_cwa_historical_model(dataset, readiness, cfg, _resolve_path(output_dir, project), _resolve_path(report_dir, project))


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
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/models/nearby_cwa_v32")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v32")
    args = parser.parse_args()
    result = run_train_nearby_cwa_historical_model(args.config, args.dataset, args.output_dir, args.report_dir)
    print(json.dumps(result["training_report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
