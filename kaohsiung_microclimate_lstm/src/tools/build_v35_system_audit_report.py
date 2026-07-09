from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ..config import ROOT
    from ..system_audit import build_v35_system_audit
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from kaohsiung_microclimate_lstm.src.config import ROOT
    from kaohsiung_microclimate_lstm.src.system_audit import build_v35_system_audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--target-area", default="KHH")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v35")
    args = parser.parse_args()
    report = build_v35_system_audit(
        config_path=args.config,
        target_area=args.target_area,
        report_dir=args.report_dir,
        project_root=ROOT,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
