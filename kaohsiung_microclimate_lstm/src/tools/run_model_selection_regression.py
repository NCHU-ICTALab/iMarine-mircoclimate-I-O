from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from ..config import ROOT, load_config
    from ..selection.model_selection_engine import select_prediction_mode
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from selection.model_selection_engine import select_prediction_mode


TAIPEI = timezone(timedelta(hours=8))


def run_model_selection_regression(config_path: str | Path, report_dir: str | Path, project_root: str | Path = ROOT) -> dict:
    cfg = load_config(config_path)
    cases = _cases()
    results = []
    for case_id, expected, context in cases:
        context["model_version"] = cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.3")
        actual = select_prediction_mode(context)
        results.append(
            {
                "case_id": case_id,
                "expected_mode": expected,
                "actual_mode": actual["selected_mode"],
                "passed": actual["selected_mode"] == expected,
                "selection": actual,
            }
        )
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.3"),
        "total_cases": len(results),
        "passed_cases": sum(1 for item in results if item["passed"]),
        "failed_cases": sum(1 for item in results if not item["passed"]),
        "cases": results,
    }
    out = _resolve_path(report_dir, Path(project_root))
    out.mkdir(parents=True, exist_ok=True)
    (out / "model_selection_regression_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _base_context() -> dict:
    return {
        "port_local_model_available": False,
        "port_local_model_accepted": False,
        "dataset_ready": False,
        "port_local_model_trained": False,
        "port_local_model_critical_under_warning_count": 0,
        "khwd_realtime_available": True,
        "valid_khwd_station_count": 6,
        "no_realtime_khwd_mode": False,
        "nearby_cwa_historical_training_enabled": True,
        "nearby_cwa_historical_model_available": True,
        "nearby_cwa_historical_model_accepted": True,
        "nearby_cwa_selected_station_ids": ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"],
        "all_nearby_cwa_stations_closer_than_467441": True,
        "nearby_cwa_critical_under_warning_count": 0,
        "fallback_baseline_available": True,
        "rain_probability_preserved": True,
        "cwa_pop_zero_is_valid_probability": True,
        "467441_used_as_core_station": False,
        "nearby_cwa_used_as_port_local_core": False,
    }


def _cases() -> list[tuple[str, str, dict]]:
    base = _base_context()
    no_khwd = {**base, "khwd_realtime_available": False, "valid_khwd_station_count": 0, "no_realtime_khwd_mode": True}
    nearby_rejected = {**no_khwd, "nearby_cwa_historical_model_accepted": False}
    port_model = {
        **base,
        "port_local_model_available": True,
        "port_local_model_accepted": True,
        "dataset_ready": True,
        "port_local_model_trained": True,
    }
    return [
        ("KHWD_REALTIME_AVAILABLE_NEARBY_ACCEPTED", "port_local_postprocess", base),
        ("KHWD_UNAVAILABLE_NEARBY_ACCEPTED", "nearby_cwa_historical_model", no_khwd),
        ("KHWD_UNAVAILABLE_NEARBY_REJECTED", "fallback_baseline", nearby_rejected),
        ("PORT_LOCAL_MODEL_ACCEPTED", "port_local_model", port_model),
    ]


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
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v33")
    args = parser.parse_args()
    print(json.dumps(run_model_selection_regression(args.config, args.report_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
