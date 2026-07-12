"""Clean observed_hourly CSV files with the shared physical range policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.historical_weather_normalizer import PHYSICAL_RANGE_LIMITS


def clean_observed_hourly_file(path: str | Path) -> dict[str, Any]:
    csv_path = Path(path)
    frame = pd.read_csv(csv_path)
    original_columns = list(frame.columns)
    report: dict[str, Any] = {
        "path": str(csv_path),
        "row_count": int(len(frame)),
        "columns_preserved": original_columns,
        "cleaned_columns": {},
    }

    for column, (low, high) in PHYSICAL_RANGE_LIMITS.items():
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid = numeric.notna() & ((numeric < low) | (numeric > high))
        invalid_count = int(invalid.sum())
        if invalid_count:
            frame.loc[invalid, column] = pd.NA
        report["cleaned_columns"][column] = {
            "range": [low, high],
            "invalid_count": invalid_count,
            "negative_count_after": int((pd.to_numeric(frame[column], errors="coerce") < 0).sum()),
        }

    duplicate_report = _deduplicate_observed_hourly(frame)
    frame = duplicate_report.pop("frame")
    report["deduplication"] = duplicate_report
    report["row_count_after_deduplication"] = int(len(frame))
    if "obs_time" in frame.columns and not frame.empty:
        obs_time = pd.to_datetime(frame["obs_time"], errors="coerce")
        report["latest_obs_time"] = None if obs_time.isna().all() else obs_time.max().isoformat()

    frame = frame[original_columns]
    frame.to_csv(csv_path, index=False)
    return report


def _deduplicate_observed_hourly(frame: pd.DataFrame) -> dict[str, Any]:
    if "obs_time" not in frame.columns:
        return {"frame": frame, "duplicate_rows_removed": 0, "dedupe_keys": []}
    keys = ["obs_time"]
    if "station_id" in frame.columns:
        keys = ["station_id", "obs_time"]
    work = frame.copy()
    work["_valid_value_count"] = work.notna().sum(axis=1)
    duplicate_rows = int(work.duplicated(keys, keep=False).sum())
    before = len(work)
    work = work.sort_values([*keys, "_valid_value_count"]).drop_duplicates(keys, keep="last")
    work = work.drop(columns=["_valid_value_count"])
    return {
        "frame": work.reset_index(drop=True),
        "dedupe_keys": keys,
        "duplicate_rows_detected": duplicate_rows,
        "duplicate_rows_removed": int(before - len(work)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to an observed_hourly CSV file.")
    parser.add_argument("--report", help="Optional JSON report path.")
    args = parser.parse_args()

    report = clean_observed_hourly_file(args.path)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
