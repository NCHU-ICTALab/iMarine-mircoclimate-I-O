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
MARINE_DATAID = "O-B0075-001"
DEFAULT_STATION_IDS = ["C4P01", "1786", "C4Q01", "C4Q02", "COMC08", "46714D"]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "raw" / "observed_hourly"


def _cwa_verify_ssl() -> bool:
    """CWA's opendata TLS chain fails strict verification on some OpenSSL builds.

    Mirrors the existing CWA_VERIFY_SSL toggle already used by app/config.py.
    """
    value = os.environ.get("CWA_VERIFY_SSL")
    if value is None:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("CWA_VERIFY_SSL="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return str(value).strip().lower() != "false" if value is not None else True

MARINE_SOURCE_NOTES = {
    "dataid": MARINE_DATAID,
    "coverage": "CWA O-B0075-001 rolling sea-surface observations; historical backfill depth must be verified with CWA.",
    "update_interval": "Official refresh is about every 4 hours; observation rows are usually hourly.",
    "storage": "Appends per-station CSV and de-duplicates by station_id/obs_time.",
}

MARINE_STATION_METADATA: dict[str, dict[str, Any]] = {
    "C4P01": {
        "station_name": "Kaohsiung Tide Station",
        "lon": 120.2883,
        "lat": 22.6144,
        "type": "tide",
        "selection_role": "primary_tide",
    },
    "1786": {
        "station_name": "Yongan Tide Station",
        "lon": 120.1975,
        "lat": 22.8189,
        "type": "tide",
        "selection_role": "nearby_tide_north",
    },
    "C4Q01": {
        "station_name": "Xiaoliuqiu Tide Station",
        "lon": 120.3833,
        "lat": 22.3533,
        "type": "tide",
        "selection_role": "nearby_tide_south",
    },
    "C4Q02": {
        "station_name": "Donggang Tide Station",
        "lon": 120.4383,
        "lat": 22.4651,
        "type": "tide",
        "selection_role": "nearby_tide_south",
    },
    "COMC08": {
        "station_name": "Mituo Data Buoy",
        "lon": 120.1636,
        "lat": 22.7636,
        "type": "buoy",
        "selection_role": "nearby_buoy_north",
    },
    "46714D": {
        "station_name": "Xiaoliuqiu Data Buoy",
        "lon": 120.3781,
        "lat": 22.3172,
        "type": "buoy",
        "selection_role": "nearby_buoy_south",
    },
}

MARINE_COLUMNS = [
    "station_id",
    "station_name",
    "obs_time",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "precipitation_1hr",
    "tide_level",
    "visibility",
    "wave_height",
    "wave_period",
    "current_speed",
    "current_direction",
    "air_pressure",
    "source",
    "data_id",
    "fetched_at",
]


def fetch_marine_history(
    api_key: str | None = None,
    dataid: str = MARINE_DATAID,
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
    response = client.get(
        f"{BASE_URL}/{dataid}",
        params={"Authorization": key, "format": "JSON"},
        timeout=30,
        verify=verify,
    )
    response.raise_for_status()

    frame = marine_payload_to_frame(
        response.json(),
        station_ids=selected_station_ids,
        dataid=dataid,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
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

    return {
        "data_id": dataid,
        "stations_requested": selected_station_ids,
        "stations_written": sorted(files),
        "rows_fetched": int(len(frame)),
        "rows_after_append_dedupe": rows_written,
        "output_files": files,
        "source_notes": MARINE_SOURCE_NOTES,
    }


def marine_payload_to_frame(
    payload: dict[str, Any],
    station_ids: list[str] | None = None,
    dataid: str = MARINE_DATAID,
    fetched_at: str | None = None,
) -> pd.DataFrame:
    selected = set(station_ids or DEFAULT_STATION_IDS)
    rows: list[dict[str, Any]] = []
    for location in extract_locations(payload):
        station = location.get("Station") if isinstance(location.get("Station"), dict) else {}
        station_id = text(station.get("StationID")) or text(station.get("StationId"))
        if not station_id or station_id not in selected:
            continue
        metadata = MARINE_STATION_METADATA.get(station_id, {})
        station_name = text(station.get("StationName")) or str(metadata.get("station_name") or station_id)
        station_times = location.get("StationObsTimes", {}).get("StationObsTime", [])
        if not isinstance(station_times, list):
            continue
        for row in station_times:
            if isinstance(row, dict):
                normalized = normalize_marine_row(
                    row,
                    station_id=station_id,
                    station_name=station_name,
                    dataid=dataid,
                    fetched_at=fetched_at,
                )
                if normalized:
                    rows.append(normalized)
    return pd.DataFrame(rows, columns=MARINE_COLUMNS)


def extract_locations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("Records") or payload.get("records") or {}
    locations = (
        records.get("SeaSurfaceObs", {}).get("Location", [])
        if isinstance(records, dict)
        else []
    )
    return [item for item in locations if isinstance(item, dict)] if isinstance(locations, list) else []


def normalize_marine_row(
    row: dict[str, Any],
    station_id: str,
    station_name: str,
    dataid: str = MARINE_DATAID,
    fetched_at: str | None = None,
) -> dict[str, Any] | None:
    obs_time = parse_cwa_time(row.get("DateTime"))
    if obs_time is None:
        return None

    elements = row.get("WeatherElements") if isinstance(row.get("WeatherElements"), dict) else {}
    anemometer = elements.get("PrimaryAnemometer") if isinstance(elements.get("PrimaryAnemometer"), dict) else {}
    current_layer = first_current_layer(elements)

    return {
        "station_id": station_id,
        "station_name": station_name,
        "obs_time": obs_time,
        "wind_speed": to_float(anemometer.get("WindSpeed")),
        "wind_gust": to_float(anemometer.get("MaximumWindSpeed")),
        "wind_direction": to_float(anemometer.get("WindDirection")),
        "precipitation_1hr": None,
        "tide_level": to_float(elements.get("TideHeight")),
        "visibility": to_float(elements.get("Visibility")),
        "wave_height": to_float(elements.get("WaveHeight")),
        "wave_period": to_float(elements.get("WavePeriod")),
        "current_speed": to_float(current_layer.get("CurrentSpeed")) if current_layer else None,
        "current_direction": to_float(current_layer.get("CurrentDirection")) if current_layer else None,
        "air_pressure": to_float(elements.get("StationPressure")),
        "source": "cwa_marine_history",
        "data_id": dataid,
        "fetched_at": fetched_at,
    }


def first_current_layer(elements: dict[str, Any]) -> dict[str, Any] | None:
    currents = elements.get("SeaCurrents")
    if not isinstance(currents, dict):
        return None
    layer = currents.get("Layer")
    if isinstance(layer, list):
        return next((item for item in layer if isinstance(item, dict)), None)
    return layer if isinstance(layer, dict) else None


def parse_cwa_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Asia/Taipei")
    return parsed.isoformat()


def to_float(value: Any) -> float | None:
    if value in (None, "", "-99", "-99.0", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--station-ids", default=",".join(DEFAULT_STATION_IDS))
    parser.add_argument("--no-append", action="store_true")
    parser.add_argument("--verify-ssl", action="store_true", default=None)
    parser.add_argument("--no-verify-ssl", action="store_false", dest="verify_ssl")
    args = parser.parse_args()

    result = fetch_marine_history(
        station_ids=[item.strip() for item in args.station_ids.split(",") if item.strip()],
        output_dir=args.output_dir,
        append=not args.no_append,
        verify_ssl=args.verify_ssl,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
