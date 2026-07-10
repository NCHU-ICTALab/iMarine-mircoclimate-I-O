from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_TIDE_STATIONS = ["C4P01", "1786", "C4Q01", "C4Q02"]
DEFAULT_BUOY_STATIONS = ["COMC08", "46714D"]


def report_surge_residual_readiness(
    observed_dir: str | Path = "kaohsiung_microclimate_lstm/data/raw/observed_hourly",
    output_dir: str | Path = "kaohsiung_microclimate_lstm/results/tide_surge_v13",
    min_days: int = 21,
    min_tide_rows: int = 24 * 14,
    tide_stations: list[str] | None = None,
    buoy_stations: list[str] | None = None,
) -> dict[str, Any]:
    observed = Path(observed_dir)
    tide_ids = tide_stations or DEFAULT_TIDE_STATIONS
    buoy_ids = buoy_stations or DEFAULT_BUOY_STATIONS
    tide_reports = [_station_report(observed / f"{station_id}.csv", station_id, ["tide_level", "air_pressure", "wind_speed", "wind_direction"], min_days, min_tide_rows) for station_id in tide_ids]
    buoy_reports = [_station_report(observed / f"{station_id}.csv", station_id, ["wave_height", "wave_period", "wind_speed", "wind_gust", "air_pressure"], min_days, min_tide_rows) for station_id in buoy_ids]
    ready_tide = [item for item in tide_reports if item["usable_for_surge_training"]]
    ready_buoy = [item for item in buoy_reports if item["wave_height_non_null"] > 0 and item["wave_period_non_null"] > 0]
    blockers = []
    if not ready_tide:
        blockers.append(f"no tide station has at least {min_tide_rows} tide rows over {min_days} days")
    if not ready_buoy:
        blockers.append("no buoy station has verified wave_height and wave_period observations")
    if max([item["coverage_days"] for item in tide_reports + buoy_reports] or [0]) < min_days:
        blockers.append(f"marine history coverage is shorter than {min_days} days")

    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "ready_for_surge_residual_training": not blockers,
        "min_required_days": min_days,
        "min_required_tide_rows": min_tide_rows,
        "blockers": blockers,
        "tide_stations": tide_reports,
        "buoy_stations": buoy_reports,
        "next_action": "keep O-B0075-001 4-hour append schedule running until enough history is accumulated" if blockers else "train surge residual ML model",
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "surge_residual_readiness_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    return report


def _station_report(path: Path, station_id: str, expected_columns: list[str], min_days: int, min_tide_rows: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "station_id": station_id,
            "exists": False,
            "rows": 0,
            "coverage_days": 0.0,
            "usable_for_surge_training": False,
            "missing_columns": expected_columns,
        }
    frame = pd.read_csv(path)
    times = pd.to_datetime(frame.get("obs_time"), errors="coerce")
    valid_times = times.dropna()
    coverage_days = 0.0
    if len(valid_times) > 1:
        coverage_days = float((valid_times.max() - valid_times.min()) / pd.Timedelta(days=1))
    non_null = {f"{col}_non_null": int(pd.to_numeric(frame[col], errors="coerce").notna().sum()) if col in frame.columns else 0 for col in expected_columns}
    tide_rows = int(pd.to_numeric(frame["tide_level"], errors="coerce").notna().sum()) if "tide_level" in frame.columns else 0
    return {
        "station_id": station_id,
        "exists": True,
        "rows": int(len(frame)),
        "start_time": valid_times.min().isoformat() if len(valid_times) else None,
        "end_time": valid_times.max().isoformat() if len(valid_times) else None,
        "coverage_days": round(coverage_days, 3),
        "missing_columns": [col for col in expected_columns if col not in frame.columns],
        **non_null,
        "usable_for_surge_training": tide_rows >= min_tide_rows and coverage_days >= float(min_days),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-dir", default="kaohsiung_microclimate_lstm/data/raw/observed_hourly")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/results/tide_surge_v13")
    parser.add_argument("--min-days", type=int, default=21)
    parser.add_argument("--min-tide-rows", type=int, default=24 * 14)
    args = parser.parse_args()
    report = report_surge_residual_readiness(args.observed_dir, args.output_dir, args.min_days, args.min_tide_rows)
    print(json.dumps({"ready": report["ready_for_surge_residual_training"], "blockers": report["blockers"], "report_path": report["report_path"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
