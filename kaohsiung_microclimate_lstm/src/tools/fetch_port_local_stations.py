from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in {None, ""}:  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from ..config import ROOT, load_config
    from ..data.port_local_station_normalizer import normalize_port_local_station_records, normalized_records_to_frame
    from ..data.port_local_station_quality import validate_port_local_station_frame
    from ..data.port_local_twport_client import PortLocalTwportClient
    from ..data.station_pool import flatten_priority_station_pool, load_station_pool_config
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from data.port_local_station_normalizer import normalize_port_local_station_records, normalized_records_to_frame
    from data.port_local_station_quality import validate_port_local_station_frame
    from data.port_local_twport_client import PortLocalTwportClient
    from data.station_pool import flatten_priority_station_pool, load_station_pool_config


TAIPEI = timezone(timedelta(hours=8))


def run_fetch_port_local_stations(
    config_path: str | Path = ROOT / "config.yaml",
    station_pool_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
    station_type: str | None = None,
    station_prefix: str | None = None,
    client: Any | None = None,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    project = Path(project_root)
    config_file = Path(config_path).resolve()
    cfg = load_config(str(config_file))
    acquisition_cfg = cfg.get("port_local_data_acquisition", {})
    pool_path = Path(station_pool_path) if station_pool_path else config_file.parent / cfg.get("station_pool", {}).get("station_pool_config", "config/station_pool.yaml")
    pool = load_station_pool_config(pool_path)
    out_dir = _resolve_path(output_dir or acquisition_cfg.get("output_dir", "data/raw/observed_hourly"), project)
    report_base = project if report_dir else config_file.parent
    rep_dir = _resolve_path(report_dir or acquisition_cfg.get("report_dir", "results/port_local_data_v28"), report_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    stations = [
        station
        for station in flatten_priority_station_pool(pool, include_reference=True)
        if bool(station.get("is_port_local", False))
    ]
    if station_type:
        stations = [station for station in stations if str(station.get("type")) == str(station_type)]
    if station_prefix:
        stations = [station for station in stations if str(station.get("station_id", "")).startswith(str(station_prefix))]

    base_url = os.getenv(str(acquisition_cfg.get("base_url_env", "TWPORT_BASE_URL")), "https://wwtf.twport.com.tw/twport/display/Realtime_Panel_Port_GatData_2024.aspx")
    if "?" not in base_url:
        base_url = f"{base_url}?{os.getenv('TWPORT_PORT_ID', '5')},1"
    client = client or PortLocalTwportClient(
        base_url=base_url,
        timeout_seconds=int(acquisition_cfg.get("timeout_seconds", 10)),
        retry_attempts=int(acquisition_cfg.get("retry_attempts", 3)),
        cache_minutes=int(acquisition_cfg.get("cache_minutes", 10)),
        verify_ssl=os.getenv("TWPORT_VERIFY_SSL", "true").lower() == "true",
    )

    generated_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
    fetch_station_results: dict[str, Any] = {}
    quality_report: dict[str, Any] = {"generated_at": generated_at, "station_quality": {}}
    normalization_report: dict[str, Any] = {"generated_at": generated_at, "station_normalization": {}}
    created_files: list[str] = []
    available: list[str] = []
    missing: list[str] = []

    for station in stations:
        station_id = str(station["station_id"])
        kind = _station_kind(station)
        result = client.fetch_station_latest(station_id)
        normalized = normalize_port_local_station_records(station_id, kind, result.get("raw_records", []), cfg)
        frame = normalized_records_to_frame(normalized)
        quality = validate_port_local_station_frame(frame, station_id, kind)

        if bool(result.get("available")) and not frame.empty and quality["valid"]:
            csv_path = out_dir / f"{station_id}.csv"
            frame.to_csv(csv_path, index=False, encoding="utf-8")
            created_files.append(csv_path.name)
            available.append(station_id)
        else:
            missing.append(station_id)

        fetch_station_results[station_id] = {
            "requested": True,
            "available": bool(result.get("available")) and not frame.empty,
            "record_count": int(len(frame)),
            "time_start": quality.get("time_start"),
            "time_end": quality.get("time_end"),
            "error": result.get("error"),
        }
        quality_report["station_quality"][station_id] = quality
        normalization_report["station_normalization"][station_id] = {
            "normalization_status": normalized.get("normalization_status"),
            "columns": normalized.get("columns"),
            "missing_columns": normalized.get("missing_columns"),
            "warnings": normalized.get("warnings"),
        }

    khwd_available = [station_id for station_id in available if station_id.startswith("KHWD")]
    availability_report = {
        "generated_at": generated_at,
        "station_pool_version": pool.get("station_pool_version"),
        "port_local_stations_configured": [str(station["station_id"]) for station in stations],
        "port_local_stations_available": available,
        "port_local_stations_missing": missing,
        "khwd_available_count": len(khwd_available),
        "khtd_available_count": len([station_id for station_id in available if station_id.startswith("KHTD")]),
        "khaw_available_count": len([station_id for station_id in available if station_id.startswith("KHAW")]),
        "port_local_wind_available": len(khwd_available) >= int(cfg.get("station_pool", {}).get("min_required_port_local_wind_stations", 2)),
        "port_local_tide_available": any(station_id.startswith("KHTD") for station_id in available),
        "port_local_wave_current_available": any(station_id.startswith("KHAW") for station_id in available),
        "fallback_to_467441_required": len(khwd_available) < int(cfg.get("station_pool", {}).get("min_required_port_local_wind_stations", 2)),
        "recommended_prediction_mode": "port_local_postprocess" if len(khwd_available) >= int(cfg.get("station_pool", {}).get("min_required_port_local_wind_stations", 2)) else "fallback_baseline",
    }
    fetch_report = {
        "generated_at": generated_at,
        "source": "twport",
        "station_results": fetch_station_results,
        "summary": {
            "requested_count": len(stations),
            "available_count": len(available),
            "missing_count": len(missing),
            "created_files": created_files,
        },
    }

    _write_json(rep_dir / "fetch_report.json", fetch_report)
    _write_json(rep_dir / "quality_report.json", quality_report)
    _write_json(rep_dir / "station_availability_report.json", availability_report)
    _write_json(rep_dir / "normalization_report.json", normalization_report)
    return {
        "port_local_data_acquisition_enabled": bool(acquisition_cfg.get("enabled", True)),
        "port_local_data_refresh_attempted": True,
        "port_local_data_refresh_success": len(available) > 0,
        "port_local_station_files_created": created_files,
        "port_local_data_report_path": str(rep_dir / "station_availability_report.json"),
        "fetch_report_path": str(rep_dir / "fetch_report.json"),
        "quality_report_path": str(rep_dir / "quality_report.json"),
        "normalization_report_path": str(rep_dir / "normalization_report.json"),
        "station_availability_report": availability_report,
        "fetch_report": fetch_report,
    }


def _station_kind(station: dict[str, Any]) -> str:
    station_type = str(station.get("type", ""))
    if station_type == "wind":
        return "wind"
    if station_type == "tide":
        return "tide"
    return "wave_current"


def _resolve_path(path: str | Path, project: Path) -> Path:
    resolved = Path(path)
    return resolved if resolved.is_absolute() else project / resolved


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--station-pool", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report-dir", default=None)
    parser.add_argument("--station-type", default=None, choices=["wind", "tide", "wave_current"])
    parser.add_argument("--station-prefix", default=None)
    args = parser.parse_args()
    project_root = Path.cwd() if args.output_dir or args.report_dir else Path(args.config).resolve().parent
    result = run_fetch_port_local_stations(
        config_path=args.config,
        station_pool_path=args.station_pool,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        station_type=args.station_type,
        station_prefix=args.station_prefix,
        project_root=project_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
