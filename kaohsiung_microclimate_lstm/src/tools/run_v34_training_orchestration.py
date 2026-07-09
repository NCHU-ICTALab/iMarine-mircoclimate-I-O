from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ..config import ROOT
    from ..training_orchestration import run_training_orchestration
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from kaohsiung_microclimate_lstm.src.config import ROOT
    from kaohsiung_microclimate_lstm.src.training_orchestration import run_training_orchestration


def _bool_arg(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--target-area", default="KHH")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v34")
    parser.add_argument("--force-train", default=False, type=_bool_arg)
    parser.add_argument("--dry-run", default=False, type=_bool_arg)
    args = parser.parse_args()
    report = run_training_orchestration(
        config_path=args.config,
        target_area=args.target_area,
        report_dir=args.report_dir,
        project_root=ROOT,
        force_train=args.force_train,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
