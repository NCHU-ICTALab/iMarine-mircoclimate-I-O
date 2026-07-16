from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from urllib3.exceptions import InsecureRequestWarning

try:
    from .check_qpesums_availability import BASE_URL, load_api_key
except ImportError:  # pragma: no cover
    from check_qpesums_availability import BASE_URL, load_api_key

try:
    from ..tools.fetch_port_local_stations import append_station_frame
except ImportError:  # pragma: no cover
    from kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations import append_station_frame

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


ROOT = Path(__file__).resolve().parents[2]
NEARBY_DATAID = "O-A0001-001"
DEFAULT_STATION_IDS = ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "raw" / "observed_hourly"

NEARBY_COLUMNS = [
    "station_id",
    "station_name",
    "obs_time",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "precipitation_1hr",
    "tide_level",
    "visibility",
    "source",
    "data_id",
    "fetched_at",
]


def _cwa_verify_ssl() -> bool:
    """Mirrors the CWA_VERIFY_SSL toggle already used by app/config.py and fetch_marine_history.py."""
    value = os.environ.get("CWA_VERIFY_SSL")
    if value is None:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("CWA_VERIFY_SSL="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return str(value).strip().lower() != "false" if value is not None else True


def to_float(value: Any) -> float | None:
    if value in (None, "", "-99", "-99.0", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_nearby_cwa_current(
    api_key: str | None = None,
    station_ids: list[str] | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    append: bool = True,
    session: Any | None = None,
    verify_ssl: bool | None = None,
) -> dict[str, Any]:
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("CWA_API_KEY is not available")

    selected_station_ids = station_ids or DEFAULT_STATION_IDS
    client = session or requests
    verify = verify_ssl if verify_ssl is not None else _cwa_verify_ssl()
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    per_station_status: dict[str, Any] = {}
    for station_id in selected_station_ids:
        response = client.get(
            f"{BASE_URL}/{NEARBY_DATAID}",
            params={"Authorization": key, "format": "JSON", "StationId": station_id},
            timeout=20,
            verify=verify,
        )
        try:
            response.raise_for_status()
            payload = response.json()
            stations = payload.get("records", payload.get("Records", {})).get("Station", [])
            if not stations:
                per_station_status[station_id] = "no_records"
                continue
            station = stations[0]
            obs_time = station.get("ObsTime", {}).get("DateTime")
            elements = station.get("WeatherElement", {})
            gust_info = elements.get("GustInfo", {})
            row = {
                "station_id": station_id,
                "station_name": station.get("StationName", station_id),
                "obs_time": obs_time,
                "wind_speed": to_float(elements.get("WindSpeed")),
                "wind_gust": to_float(gust_info.get("PeakGustSpeed")),
                "wind_direction": to_float(elements.get("WindDirection")),
                "precipitation_1hr": to_float(elements.get("Now", {}).get("Precipitation")),
                "tide_level": None,
                "visibility": None,
                "source": "cwa_nearby_current",
                "data_id": NEARBY_DATAID,
                "fetched_at": fetched_at,
            }
            rows.append(row)
            per_station_status[station_id] = "ok"
        except Exception as exc:  # noqa: BLE001
            per_station_status[station_id] = f"error: {exc}"

    frame = pd.DataFrame(rows, columns=NEARBY_COLUMNS)
    output_path = Path(output_dir)
    files: dict[str, str] = {}
    rows_written: dict[str, int] = {}
    for station_id, station_frame in frame.groupby("station_id", sort=True):
        csv_path = output_path / f"{station_id}.csv"
        if append:
            written = append_station_frame(csv_path, station_frame)
        else:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            station_frame.to_csv(csv_path, index=False, encoding="utf-8")
            written = station_frame
        files[str(station_id)] = str(csv_path)
        rows_written[str(station_id)] = int(len(written))

    all_stations_failed = int(len(frame)) == 0 and len(selected_station_ids) > 0
    return {
        "data_id": NEARBY_DATAID,
        "stations_requested": selected_station_ids,
        "per_station_status": per_station_status,
        "rows_fetched": int(len(frame)),
        "all_stations_failed": all_stations_failed,
        "rows_after_append_dedupe": rows_written,
        "output_files": files,
        "source_notes": {
            "coverage": "CWA O-A0001-001 current automatic-station observation (single latest reading per call, not a history query).",
            "precipitation_caveat": "Precipitation is CWA's 'Now' accumulation field, not guaranteed to be a clean rolling 1-hour sum; treat as best-available real-time rain signal, not an exact 1hr total.",
            "storage": "Appends per-station CSV and de-duplicates by station_id/obs_time, same convention as fetch_marine_history.py / fetch_port_local_stations.py.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--station-ids", default=",".join(DEFAULT_STATION_IDS))
    parser.add_argument("--no-append", action="store_true")
    args = parser.parse_args()

    result = fetch_nearby_cwa_current(
        station_ids=[item.strip() for item in args.station_ids.split(",") if item.strip()],
        output_dir=args.output_dir,
        append=not args.no_append,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
