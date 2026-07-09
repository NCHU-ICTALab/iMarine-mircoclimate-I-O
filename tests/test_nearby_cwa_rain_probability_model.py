import pandas as pd

from kaohsiung_microclimate_lstm.src.training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model


def _dataset(periods=120):
    times = pd.date_range("2026-07-01 00:00", periods=periods, freq="1h")
    speed = pd.Series(range(periods), dtype=float) / 10.0
    return pd.DataFrame(
        {
            "obs_time": times,
            "nearby_cwa_wind_speed_max": speed,
            "nearby_cwa_wind_gust_max": speed + 2.0,
            "nearby_cwa_precipitation_1hr_max": [0, 1] * (periods // 2),
            "target_nearby_wind_speed_H1": speed.shift(-1).bfill(),
            "target_nearby_wind_gust_H1": (speed + 2.0).shift(-1).bfill(),
            "target_rain_event_H1": [0, 1] * (periods // 2),
        }
    )


def test_nearby_cwa_rain_probability_model_outputs_brier_score(tmp_path):
    result = train_nearby_cwa_historical_model(
        _dataset(),
        {"ready": True, "failed_reasons": [], "selected_station_ids": ["C0V890", "C0V490"]},
        {},
        tmp_path / "models",
        tmp_path / "reports",
    )

    assert "Brier Score" in result["metrics"]["rain_probability"]["H1"]
    assert (tmp_path / "reports" / "nearby_cwa_rain_probability_metrics.json").exists()
