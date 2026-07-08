from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


CODIS_URL = "https://codis.cwa.gov.tw/api/station"
TARGET_STATIONS = ["C0V840", "C0V890", "C0V810", "C0V450", "C0V700", "C0V690", "C0V710", "CAP070"]
STATION_TYPES = ["cwb/auto", "cwb/auto_C0", "cwb/mps", "cwb/rain", "cwb/auto_M", "cwb"]
DATA_TYPES = ["10min", "hour", "day"]


def default_date_ranges() -> list[tuple[str, str]]:
    today = date.today()
    return [
        ((today - timedelta(days=7)).isoformat(), today.isoformat()),
        ((today - timedelta(days=1)).isoformat(), today.isoformat()),
        ((today - timedelta(days=180)).isoformat(), today.isoformat()),
    ]


def query_codis(station_id: str, station_type: str, data_type: str, start: str, end: str) -> list[dict[str, Any]]:
    payloads = [
        {
            "type": "report_date",
            "stn_ID": station_id,
            "stn_type": station_type,
            "start": f"{start}T00:00:00",
            "end": f"{end}T23:59:59",
            "item": "AirTemperature",
        },
        {
            "StationId": station_id,
            "stationType": station_type,
            "dataType": data_type,
            "startDate": start,
            "endDate": end,
        },
    ]
    headers = {"User-Agent": "Mozilla/5.0 microclimate-codis-diagnosis/1.0"}
    for payload in payloads:
        try:
            if "type" in payload:
                resp = requests.post(CODIS_URL, data=payload, timeout=30, verify=False, headers=headers)
            else:
                resp = requests.get(CODIS_URL, params=payload, timeout=30, verify=False, headers=headers)
            resp.raise_for_status()
            rows = extract_rows(resp.json())
            if rows:
                return rows
        except Exception:
            continue
    return []


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and isinstance(data[0].get("dts"), list):
            rows: list[dict[str, Any]] = []
            for station in data:
                rows.extend(item for item in station.get("dts", []) if isinstance(item, dict))
            return rows
        return [item for item in data if isinstance(item, dict)]
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        return [item for item in rows if isinstance(item, dict)]
    return []


def diagnose_all(
    stations: list[str] | None = None,
    output_path: str | Path = "kaohsiung_microclimate_lstm/results/codis_diagnosis.csv",
) -> Path:
    results: list[dict[str, Any]] = []
    for station_id in stations or TARGET_STATIONS:
        for station_type in STATION_TYPES:
            for data_type in DATA_TYPES:
                for start, end in default_date_ranges():
                    try:
                        rows = query_codis(station_id, station_type, data_type, start, end)
                        n = len(rows)
                        cols = list(rows[0].keys()) if n else []
                    except Exception as exc:
                        n, cols = -1, [str(exc)]
                    results.append(
                        {
                            "station_id": station_id,
                            "stationType": station_type,
                            "dataType": data_type,
                            "date_range": f"{start}~{end}",
                            "row_count": n,
                            "columns": ",".join(map(str, cols[:8])),
                        }
                    )
                    if n > 0:
                        break
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["station_id", "stationType", "dataType", "date_range", "row_count", "columns"])
        writer.writeheader()
        writer.writerows(results)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/results/codis_diagnosis.csv")
    parser.add_argument("--stations", nargs="*")
    args = parser.parse_args()
    print(diagnose_all(args.stations, args.output))


if __name__ == "__main__":
    main()
