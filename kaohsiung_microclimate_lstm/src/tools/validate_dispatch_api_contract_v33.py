from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from ..config import ROOT, load_config
    from ..predict import predict_dispatch_risk_v33
    from ..preprocess import load_observations
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from kaohsiung_microclimate_lstm.src.config import ROOT, load_config
    from kaohsiung_microclimate_lstm.src.predict import predict_dispatch_risk_v33
    from kaohsiung_microclimate_lstm.src.preprocess import load_observations


TAIPEI = timezone(timedelta(hours=8))


def validate_dispatch_api_contract_v33(
    config_path: str | Path,
    api_url: str,
    report_dir: str | Path,
    scenario: str | None = None,
    project_root: str | Path = ROOT,
) -> dict:
    project = Path(project_root)
    cfg = load_config(config_path)
    query = parse_qs(urlparse(api_url).query)
    no_khwd = str(query.get("no_realtime_khwd_mode", ["false"])[0]).lower() == "true"
    fallback_path = project / "data" / "raw" / "observed_hourly" / "467441.csv"
    observations = load_observations(fallback_path)
    payload = predict_dispatch_risk_v33(fallback_observations=observations, config_path=str(config_path), project_root=project, no_realtime_khwd_mode=no_khwd)
    checks = _checks(payload, no_khwd)
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_version": cfg.get("project", {}).get("model_version", "kaohsiung_port_dispatch_risk_v3.3"),
        "scenario": scenario or ("KHWD_UNAVAILABLE_NEARBY_ACCEPTED" if no_khwd else "KHWD_REALTIME_AVAILABLE_NEARBY_ACCEPTED"),
        "api_url": api_url,
        "passed": all(checks.values()),
        "checks": checks,
        "snapshot_path": "api_contract_snapshot_v33.json",
    }
    out = _resolve_path(report_dir, project)
    out.mkdir(parents=True, exist_ok=True)
    (out / "api_contract_validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "api_contract_snapshot_v33.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _checks(payload: dict, no_khwd: bool) -> dict[str, bool]:
    trace = payload.get("trace", {})
    expected_mode = "nearby_cwa_historical_model" if no_khwd else "port_local_postprocess"
    return {
        "model_version_v33": payload.get("model_version") == "kaohsiung_port_dispatch_risk_v3.3",
        "expected_prediction_mode": payload.get("prediction_mode") == expected_mode,
        "467441_not_core": trace.get("467441_used_as_core_station") is False,
        "nearby_cwa_not_core": trace.get("nearby_cwa_used_as_port_local_core") is False,
        "cwa_pop_not_model_input": trace.get("cwa_pop_used_as_model_input") is False,
        "rain_probability_preserved": trace.get("rain_probability_preserved") is True,
        "evaluated_modes_present": bool(payload.get("model_selection_summary", {}).get("evaluated_modes")),
    }


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
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v33")
    args = parser.parse_args()
    print(json.dumps(validate_dispatch_api_contract_v33(args.config, args.api_url, args.report_dir, args.scenario), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
