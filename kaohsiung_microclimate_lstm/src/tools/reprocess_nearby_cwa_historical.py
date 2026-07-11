from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from ..config import ROOT
    from ..data.historical_weather_normalizer import load_historical_weather_csv, write_normalized_parquet
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT
    from data.historical_weather_normalizer import load_historical_weather_csv, write_normalized_parquet


TAIPEI = timezone(timedelta(hours=8))


def reprocess_nearby_cwa_historical(
    raw_dir: str | Path,
    output_dir: str | Path,
    station_ids: list[str] | None = None,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    project = Path(project_root)
    raw_path = _resolve_path(raw_dir, project)
    output_path = _resolve_path(output_dir, project)
    output_path.mkdir(parents=True, exist_ok=True)
    selected = station_ids or sorted(path.name for path in raw_path.iterdir() if path.is_dir())
    records = []
    for station_id in selected:
        files = sorted((raw_path / station_id).glob("*.csv")) if (raw_path / station_id).exists() else sorted(raw_path.glob(f"{station_id}*.csv"))
        if not files:
            records.append({"station_id": station_id, "success": False, "error": "raw_csv_missing"})
            continue
        frame = load_historical_weather_csv(files[-1], station_id)
        storage = write_normalized_parquet(frame, output_path / f"{station_id}.parquet")
        records.append(
            {
                "station_id": station_id,
                "success": True,
                "raw_path": str(files[-1]),
                "processed_path": str(output_path / f"{station_id}.parquet"),
                "storage_format": storage,
                "row_count": int(len(frame)),
                "negative_wind_speed_count": int((frame.get("wind_speed", []) < 0).sum()) if "wind_speed" in frame else 0,
                "negative_precipitation_count": int((frame.get("precipitation_1hr", []) < 0).sum()) if "precipitation_1hr" in frame else 0,
            }
        )
    return {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "raw_dir": str(raw_path),
        "output_dir": str(output_path),
        "records": records,
        "success_count": sum(1 for record in records if record.get("success")),
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
    parser.add_argument("--raw-dir", default="kaohsiung_microclimate_lstm/data/raw/historical_weather")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/data/processed/nearby_cwa_historical")
    parser.add_argument("--station-ids", default=None)
    parser.add_argument("--report", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v32/reprocess_nearby_cwa_historical_report.json")
    args = parser.parse_args()
    station_ids = [item.strip() for item in args.station_ids.split(",") if item.strip()] if args.station_ids else None
    report = reprocess_nearby_cwa_historical(args.raw_dir, args.output_dir, station_ids)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
