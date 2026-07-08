from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
CANDIDATE_DATAIDS = ["O-A0059-001", "O-A0002-001", "O-A0064-001", "O-A0065-001"]


def load_api_key() -> str | None:
    if os.environ.get("CWA_API_KEY"):
        return os.environ["CWA_API_KEY"]
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("CWA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def check_availability(output_path: str | Path = "kaohsiung_microclimate_lstm/results/qpesums_availability.json") -> dict[str, Any]:
    api_key = load_api_key()
    results: dict[str, Any] = {}
    if not api_key:
        results["_status"] = {"qpesums_available": False, "reason": "missing CWA_API_KEY"}
    for dataid in CANDIDATE_DATAIDS:
        if not api_key:
            results[dataid] = {"api_success": False, "record_count": 0, "reason": "missing CWA_API_KEY"}
            continue
        try:
            resp = requests.get(
                f"{BASE_URL}/{dataid}",
                params={"Authorization": api_key, "format": "JSON"},
                timeout=20,
                verify=False,
            )
            body = resp.json()
            records = body.get("records", {}) if isinstance(body, dict) else {}
            stations = records.get("Station", []) if isinstance(records, dict) else []
            results[dataid] = {
                "http_status": resp.status_code,
                "api_success": body.get("success") if isinstance(body, dict) else None,
                "record_count": len(stations),
                "sample_fields": list(stations[0].keys()) if stations and isinstance(stations[0], dict) else [],
            }
        except Exception as exc:
            results[dataid] = {"api_success": False, "record_count": 0, "error": sanitize_error(str(exc))}
    if "_status" not in results:
        results["_status"] = {
            "qpesums_available": any(int(v.get("record_count", 0)) > 0 for k, v in results.items() if not k.startswith("_")),
        }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def sanitize_error(message: str) -> str:
    api_key = load_api_key()
    if api_key:
        message = message.replace(api_key, "<CWA_API_KEY>")
    return message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/results/qpesums_availability.json")
    args = parser.parse_args()
    print(json.dumps(check_availability(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
