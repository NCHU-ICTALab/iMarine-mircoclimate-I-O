from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaohsiung_microclimate_lstm.src.cwa.pop3h_client import DATAID, fetch_pop3h


def verify(location_name: str, project_root: str | Path) -> dict:
    result = fetch_pop3h(
        location_name,
        cache_minutes=0,
        project_root=project_root,
        data_id=DATAID,
        include_wind_speed=True,
    )
    current_wind = result.get("current_wind") or {}
    next_wind = result.get("next_wind") or {}
    checks = {
        "rain_probability_available": bool(result.get("available") and result.get("current") is not None and result.get("next") is not None),
        "rain_probability_range_ok": all(
            value is not None and 0.0 <= float(value) <= 1.0 for value in [result.get("current"), result.get("next")]
        ),
        "beaufort_available": current_wind.get("beaufort_scale_min") is not None and next_wind.get("beaufort_scale_min") is not None,
        "wind_speed_is_not_precise_mps": result.get("current_wind_speed_mps") is None and result.get("next_wind_speed_mps") is None,
    }
    return {
        "available": bool(result.get("available")),
        "data_id": result.get("data_id"),
        "location_name": result.get("location_name"),
        "fetched_at": result.get("fetched_at"),
        "current_rain_probability": result.get("current"),
        "next_rain_probability": result.get("next"),
        "current_wind": current_wind,
        "next_wind": next_wind,
        "checks": checks,
        "passed": all(checks.values()),
        "sample_records": result.get("records", [])[:2],
        **({"reason": result.get("reason")} if result.get("reason") else {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live CWA +3h/+6h extended forecast parsing.")
    parser.add_argument("--location-name", default="前鎮區")
    parser.add_argument("--project-root", default="kaohsiung_microclimate_lstm")
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/results/dispatch_risk_v35/cwa_extended_forecast_live_verification.json")
    args = parser.parse_args()

    report = verify(args.location_name, args.project_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
