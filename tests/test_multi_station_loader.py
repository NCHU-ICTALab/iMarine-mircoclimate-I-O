import pandas as pd
import pytest

from kaohsiung_microclimate_lstm.src.data.multi_station_loader import load_multi_station_observations


def _write_station(path, station_id):
    pd.DataFrame(
        {
            "station_id": [station_id],
            "obs_time": ["2026-07-08T00:00:00+08:00"],
            "wind_speed": [1.0],
            "wind_gust": [2.0],
            "precipitation_1hr": [0.0],
        }
    ).to_csv(path / f"{station_id}.csv", index=False)


def test_load_multi_station_observations_reports_available_and_missing(tmp_path):
    _write_station(tmp_path, "467441")
    _write_station(tmp_path, "C4Q01")
    pool = [{"station_id": "467441"}, {"station_id": "C4Q01"}, {"station_id": "C4Q02"}]

    result = load_multi_station_observations(pool, tmp_path, "467441")

    assert result["multi_station_input"] is True
    assert result["fallback_to_single_station"] is False
    assert result["input_station_count"] == 2
    assert result["available_station_ids"] == ["467441", "C4Q01"]
    assert result["missing_station_ids"] == ["C4Q02"]


def test_load_multi_station_observations_marks_single_station_fallback(tmp_path):
    _write_station(tmp_path, "467441")
    pool = [{"station_id": "467441"}, {"station_id": "C4Q01"}]

    result = load_multi_station_observations(pool, tmp_path, "467441")

    assert result["multi_station_input"] is False
    assert result["fallback_to_single_station"] is True
    assert result["fallback_reason"] == "Only target station data available."


def test_load_multi_station_observations_requires_target(tmp_path):
    pool = [{"station_id": "467441"}, {"station_id": "C4Q01"}]

    with pytest.raises(FileNotFoundError):
        load_multi_station_observations(pool, tmp_path, "467441")
