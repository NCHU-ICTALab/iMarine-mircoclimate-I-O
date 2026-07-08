from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

try:
    from .diagnose_codis_stations import CODIS_URL, extract_rows
except ImportError:  # pragma: no cover
    from diagnose_codis_stations import CODIS_URL, extract_rows


QUERY_CONFIGS = [
    {"stationType": "cwb/auto", "dataType": "10min"},
    {"stationType": "cwb/auto", "dataType": "hour"},
    {"stationType": "cwb/mps", "dataType": "10min"},
    {"stationType": "cwb/auto_C0", "dataType": "10min"},
    {"stationType": "cwb", "dataType": "hour"},
]


def fetch_station(station_id: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, dict[str, str]]:
    headers = {"User-Agent": "Mozilla/5.0 microclimate-codis-fetch/1.0"}
    for cfg in QUERY_CONFIGS:
        payloads = [
            {
                "StationId": station_id,
                "dataType": cfg["dataType"],
                "startDate": start_date,
                "endDate": end_date,
                "stationType": cfg["stationType"],
            },
            {
                "type": "report_date",
                "stn_ID": station_id,
                "stn_type": cfg["stationType"],
                "start": f"{start_date}T00:00:00",
                "end": f"{end_date}T23:59:59",
                "item": "AirTemperature",
            },
        ]
        for payload in payloads:
            try:
                if "type" in payload:
                    resp = requests.post(CODIS_URL, data=payload, timeout=30, verify=False, headers=headers)
                else:
                    resp = requests.get(CODIS_URL, params=payload, timeout=30, verify=False, headers=headers)
                resp.raise_for_status()
                rows = extract_rows(resp.json())
                if rows:
                    return normalize_rows(rows, station_id), cfg
            except Exception:
                continue
    raise ValueError(f"All CODiS query combinations returned 0 rows: {station_id}")


def normalize_rows(rows: list[dict[str, Any]], station_id: str) -> pd.DataFrame:
    records = []
    for row in rows:
        obs_time = row.get("DataTime") or row.get("obs_time") or row.get("ObsTime") or row.get("time")
        if not obs_time:
            continue
        records.append(
            {
                "station_id": station_id,
                "obs_time": obs_time,
                "wind_speed": nested_float(row, "WindSpeed", "Mean") or to_float(row.get("wind_speed")),
                "wind_gust": nested_float(row, "PeakGust", "Maximum") or to_float(row.get("wind_gust")),
                "wind_direction": nested_float(row, "WindDirection", "Mean") or to_float(row.get("wind_direction")),
                "precipitation_10min": nested_float(row, "Precipitation", "Accumulation") or to_float(row.get("precipitation_10min")),
                "precipitation_1hr": nested_float(row, "Precipitation", "Accumulation") or to_float(row.get("precipitation_1hr")),
                "visibility": visibility_meters(row),
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df["obs_time"] = pd.to_datetime(df["obs_time"])
        df = df.drop_duplicates("obs_time").sort_values("obs_time")
    return df


def nested_float(row: dict[str, Any], key: str, nested_key: str) -> float | None:
    value = row.get(key)
    if not isinstance(value, dict):
        return None
    return to_float(value.get(nested_key))


def visibility_meters(row: dict[str, Any]) -> float | None:
    value = nested_float(row, "Visibility", "AutoMean") or nested_float(row, "Visibility", "Instantaneous")
    return value * 1000 if value is not None else None


def to_float(value: Any) -> float | None:
    if value in ("", None, "-", "-99", "-999", "NaN"):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", default="467441")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/data/raw/codis_10min/467441.csv")
    args = parser.parse_args()
    end = date.today()
    start = end - timedelta(days=args.days)
    df, cfg = fetch_station(args.station_id, start.isoformat(), end.isoformat())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8")
    print({"output": str(output), "rows": len(df), "query_config": cfg})


if __name__ == "__main__":
    main()
