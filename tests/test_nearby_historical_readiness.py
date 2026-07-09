import pandas as pd

from kaohsiung_microclimate_lstm.src.data.nearby_historical_readiness import check_nearby_historical_training_readiness


def _config():
    return {
        "nearby_cwa_historical_training": {
            "min_selected_stations": 2,
            "training_thresholds": {
                "min_total_samples": 10,
                "min_training_days": 1,
                "min_valid_wind_samples": 10,
                "min_valid_gust_samples": 10,
                "min_valid_rain_samples": 10,
            },
        }
    }


def test_nearby_historical_readiness_ready_true():
    times = pd.date_range("2026-07-01 00:00", periods=80, freq="1h")
    frames = {
        sid: pd.DataFrame({"obs_time": times, "wind_speed": 3.0, "wind_gust": 5.0, "precipitation_1hr": 0.0})
        for sid in ["C0V890", "C0V490"]
    }

    result = check_nearby_historical_training_readiness(frames, ["C0V890", "C0V490"], _config())

    assert result["ready"] is True
    assert result["station_count"] == 2


def test_nearby_historical_readiness_fails_when_too_few_stations():
    result = check_nearby_historical_training_readiness({}, ["C0V890"], _config())

    assert result["ready"] is False
    assert result["failed_reasons"]
