from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ..config import ROOT, load_config
    from ..training.train_port_local_model import train_port_local_model
    from .build_port_local_training_dataset import load_port_local_training_dataset
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from training.train_port_local_model import train_port_local_model
    from tools.build_port_local_training_dataset import load_port_local_training_dataset


def run_train_port_local_model(
    config_path: str | Path = "config.yaml",
    dataset_path: str | Path = "data/processed/port_local_training_dataset.parquet",
    output_dir: str | Path = "models/port_local_v30",
    report_dir: str | Path = "results/dispatch_risk_v30",
    project_root: str | Path = ROOT,
) -> dict:
    project = Path(project_root)
    cfg = load_config(config_path)
    dataset = load_port_local_training_dataset(_resolve_path(dataset_path, project))
    return train_port_local_model(
        dataset=dataset,
        config=cfg,
        output_dir=_resolve_path(output_dir, project),
        report_dir=_resolve_path(report_dir, project),
    )


def _resolve_path(path: str | Path, project: Path) -> Path:
    out = Path(path)
    if out.is_absolute() or out.exists():
        return out
    if out.parts and out.parts[0] == project.name:
        return Path.cwd() / out
    return project / out


def main() -> None:
    parser = argparse.ArgumentParser(description="Train v3.0 KHWD port-local baseline models.")
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--dataset", default="kaohsiung_microclimate_lstm/data/processed/port_local_training_dataset.parquet")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/models/port_local_v30")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v30")
    args = parser.parse_args()
    result = run_train_port_local_model(
        config_path=args.config,
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        project_root=ROOT,
    )
    print(json.dumps(result["training_report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
