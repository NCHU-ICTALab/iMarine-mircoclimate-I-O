from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from ..config import ROOT, load_config
    from ..data.nearby_station_ranker import rank_nearby_cwa_stations
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.nearby_station_ranker import rank_nearby_cwa_stations


def run_rank_nearby_cwa_stations(config_path: str | Path, report_dir: str | Path, project_root: str | Path = ROOT) -> dict:
    project = Path(project_root)
    cfg = load_config(config_path)
    metadata = _station_metadata_from_config(cfg)
    ranking = rank_nearby_cwa_stations(
        metadata,
        cfg.get("kaohsiung_port_reference_points", []),
        cfg.get("nearby_cwa_historical_training", {}).get("baseline_station_id", "467441"),
        cfg,
    )
    out = _resolve_path(report_dir, project)
    out.mkdir(parents=True, exist_ok=True)
    (out / "nearby_station_ranking_report.json").write_text(json.dumps(ranking["ranking_report"], ensure_ascii=False, indent=2), encoding="utf-8")
    return ranking


def _station_metadata_from_config(cfg: dict) -> list[dict]:
    training = cfg.get("nearby_cwa_historical_training", {})
    stations = []
    for group in ["priority_1_near_port", "priority_2_outer_nearby"]:
        stations.extend({**station, "priority_group": group} for station in cfg.get("nearby_cwa_historical_station_pool", {}).get(group, []))
    baseline = cfg.get("fallback_baseline_station") or {
        "station_id": training.get("baseline_station_id", "467441"),
        "name": "Kaohsiung",
        "longitude": 120.312516,
        "latitude": 22.730432,
        "role": "fallback_baseline",
    }
    stations.append(baseline)
    return stations


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
    parser.add_argument("--station-metadata-source", default="config")
    parser.add_argument("--baseline-station-id", default="467441")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v32")
    args = parser.parse_args()
    result = run_rank_nearby_cwa_stations(args.config, args.report_dir)
    print(json.dumps(result["ranking_report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
