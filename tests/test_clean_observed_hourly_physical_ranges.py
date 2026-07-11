from pathlib import Path

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.clean_observed_hourly_physical_ranges import clean_observed_hourly_file


def test_clean_observed_hourly_file_reuses_physical_ranges_and_preserves_columns(tmp_path: Path):
    csv_path = tmp_path / "467441.csv"
    columns = ["station_id", "obs_time", "wind_speed", "precipitation_1hr", "visibility"]
    pd.DataFrame(
        [
            ["467441", "2026-01-01T00:00:00+08:00", 1.2, -9.8, 10000.0],
            ["467441", "2026-01-01T01:00:00+08:00", -99.7, 3.0, 150000.0],
        ],
        columns=columns,
    ).to_csv(csv_path, index=False)

    report = clean_observed_hourly_file(csv_path)
    cleaned = pd.read_csv(csv_path)

    assert list(cleaned.columns) == columns
    assert pd.isna(cleaned.loc[0, "precipitation_1hr"])
    assert pd.isna(cleaned.loc[1, "wind_speed"])
    assert pd.isna(cleaned.loc[1, "visibility"])
    assert report["cleaned_columns"]["precipitation_1hr"]["invalid_count"] == 1
    assert report["cleaned_columns"]["wind_speed"]["invalid_count"] == 1
    assert report["cleaned_columns"]["visibility"]["invalid_count"] == 1
