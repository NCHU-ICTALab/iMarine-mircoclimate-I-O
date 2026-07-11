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

    frame = frame[original_columns]
    frame.to_csv(csv_path, index=False)
    return report


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
