from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

try:
    from ..config import ROOT, load_config
    from ..data.historical_weather_normalizer import normalize_historical_weather_frame, write_normalized_parquet
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import ROOT, load_config
    from data.historical_weather_normalizer import normalize_historical_weather_frame, write_normalized_parquet


TAIPEI = timezone(timedelta(hours=8))
DOWNLOAD_URL = "https://mycolab.pp.nchu.edu.tw/historical_weather/index.php"


def run_backfill_nearby_cwa_historical(
    config_path: str | Path,
    station_ids: list[str],
    start_date: str,
    end_date: str,
    source_mode: str,
    output_dir: str | Path,
    report_dir: str | Path,
    project_root: str | Path = ROOT,
) -> dict:
    project = Path(project_root)
    load_config(config_path)
    raw_dir = _resolve_path(output_dir, project)
    processed_dir = project / "data" / "processed" / "nearby_cwa_historical"
    report_path = _resolve_path(report_dir, project)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_path.mkdir(parents=True, exist_ok=True)
    effective_end = _resolve_end_date(end_date)
    records = []
    for station_id in station_ids:
        try:
            raw = _download_station(station_id, start_date, effective_end) if source_mode == "downloader_get" else pd.DataFrame()
            raw_csv = raw_dir / station_id / f"{station_id}_{start_date}_{effective_end}.csv"
            raw_csv.parent.mkdir(parents=True, exist_ok=True)
            raw.to_csv(raw_csv, index=False, encoding="utf-8-sig")
            normalized = normalize_historical_weather_frame(raw, station_id)
            storage = write_normalized_parquet(normalized, processed_dir / f"{station_id}.parquet")
            records.append({"station_id": station_id, "success": True, "row_count": int(len(normalized)), "raw_path": str(raw_csv), "processed_path": str(processed_dir / f"{station_id}.parquet"), "storage_format": storage})
        except Exception as exc:
            records.append({"station_id": station_id, "success": False, "error": str(exc)})
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "source_mode": source_mode,
        "start_date": start_date,
        "end_date": effective_end,
        "records": records,
        "success_count": sum(1 for item in records if item.get("success")),
    }
    (report_path / "nearby_cwa_backfill_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _download_station(station_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    response = requests.get(
        DOWNLOAD_URL,
        params={"station_id": station_id, "startdate": start_date, "enddate": end_date, "observation_type": "hourly"},
        timeout=60,
    )
    response.raise_for_status()
    from io import StringIO

    text = response.text.strip()
    if not text:
        raise ValueError("empty downloader response")
    return pd.read_csv(StringIO(text))


def _resolve_end_date(value: str) -> str:
    if value == "yesterday":
        return (datetime.now(TAIPEI) - timedelta(days=1)).strftime("%Y%m%d")
    return value


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
    parser.add_argument("--station-ids", required=True)
    parser.add_argument("--baseline-station-id", default="467441")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="yesterday")
    parser.add_argument("--source-mode", default="downloader_get")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/data/raw/historical_weather")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v32")
    args = parser.parse_args()
    report = run_backfill_nearby_cwa_historical(args.config, [sid.strip() for sid in args.station_ids.split(",") if sid.strip()], args.start_date, args.end_date, args.source_mode, args.output_dir, args.report_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
