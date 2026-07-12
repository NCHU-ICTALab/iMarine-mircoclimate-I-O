from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT


TAIPEI = timezone(timedelta(hours=8))


def build_low_risk_cleanup_report(project_root: str | Path = ROOT) -> dict[str, Any]:
    project = Path(project_root)
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "items": {
            "port_local_training_dataset": _port_local_dataset_status(project),
            "extra_historical_weather_stations": _extra_historical_weather_status(project),
            "orphan_config_smoke": _path_status(project / "config_smoke.yaml"),
            "legacy_setup_project_structure_sh": _path_status(project.parent / "scripts" / "setup_project_structure.sh"),
            "legacy_cwa_pop_cache_files": _legacy_cwa_cache_status(project),
        },
        "action_policy": "report_only_no_delete",
    }


def write_low_risk_cleanup_report(project_root: str | Path = ROOT, output: str | Path | None = None) -> dict[str, Any]:
    project = Path(project_root)
    report = build_low_risk_cleanup_report(project)
    out = Path(output) if output is not None else project / "results" / "dispatch_risk_v35" / "low_risk_cleanup_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _port_local_dataset_status(project: Path) -> dict[str, Any]:
    path = project / "data" / "processed" / "port_local_training_dataset.parquet"
    if not path.exists():
        return {"path": str(path), "exists": False, "warning": "dataset_missing"}
    frame = pd.read_parquet(path)
    target_cols = [col for col in frame.columns if col.startswith("target_")]
    label_valid_count = {col: int(frame[col].notna().sum()) for col in target_cols}
    return {
        "path": str(path),
        "exists": True,
        "sample_count": int(len(frame)),
        "target_columns": target_cols,
        "label_valid_count": label_valid_count,
        "warning": "dataset_present_but_not_training_ready" if len(frame) < 500 or any(count == 0 for count in label_valid_count.values()) else None,
    }


def _extra_historical_weather_status(project: Path) -> dict[str, Any]:
    raw_dir = project / "data" / "raw" / "historical_weather"
    selected = {"C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"}
    extras = []
    for path in raw_dir.rglob("*.csv"):
        station = path.stem.split("_")[0]
        if station and station not in selected and station.startswith("C0V"):
            extras.append(station)
    return {"raw_dir": str(raw_dir), "extra_station_ids": sorted(set(extras)), "warning": "extra_raw_stations_not_used_for_training" if extras else None}


def _legacy_cwa_cache_status(project: Path) -> dict[str, Any]:
    cache_dir = project / "data" / "cache"
    legacy = [path.name for path in cache_dir.glob("cwa_pop3h_*.json") if "F-D" not in path.name and "F-C" not in path.name]
    return {"cache_dir": str(cache_dir), "legacy_cache_files": sorted(legacy), "warning": "legacy_cache_files_not_deleted" if legacy else None}


def _path_status(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "warning": "orphan_or_legacy_file_present" if path.exists() else None}


def main() -> None:
    report = write_low_risk_cleanup_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
