import pandas as pd

from kaohsiung_microclimate_lstm.src.training.train_nearby_cwa_historical_model import train_nearby_cwa_historical_model


def _dataset(periods=120):
    times = pd.date_range("2026-07-01 00:00", periods=periods, freq="1h")
    speed = pd.Series(range(periods), dtype=float) / 10.0
    gust = speed + 2.0
    data = {
        "obs_time": times,
        "nearby_cwa_wind_speed_max": speed,
        "nearby_cwa_wind_speed_mean": speed - 0.1,
        "nearby_cwa_wind_gust_max": gust,
        "nearby_cwa_precipitation_1hr_max": [0, 1] * (periods // 2),
        "nearby_cwa_precipitation_1hr_mean": [0, 0.5] * (periods // 2),
        "nearby_cwa_precipitation_1hr_max_lag1": [0, 1] * (periods // 2),
        "nearby_cwa_precipitation_1hr_max_roll3": [0, 0.5] * (periods // 2),
        "nearby_cwa_precipitation_roll3": [0, 0.5] * (periods // 2),
        "nearby_cwa_precipitation_roll6": [0, 0.5] * (periods // 2),
        "nearby_cwa_rainy_station_count": [0, 1] * (periods // 2),
        "nearby_cwa_rainy_station_ratio": [0, 0.5] * (periods // 2),
        "distance_weighted_precipitation": [0, 0.75] * (periods // 2),
        "hour_sin": 0.0,
        "hour_cos": 1.0,
        "doy_sin": 0.0,
        "doy_cos": 1.0,
        "nearby_cwa_station_count": 2,
    }
    for idx, horizon in enumerate(["H1", "H2", "H3", "H4"], start=1):
        data[f"target_nearby_wind_speed_{horizon}"] = speed.shift(-idx).bfill()
        data[f"target_nearby_wind_gust_{horizon}"] = gust.shift(-idx).bfill()
        data[f"target_rain_event_{horizon}"] = [0, 1] * (periods // 2)
        data[f"target_nearby_precipitation_amount_{horizon}"] = pd.Series([0, 1] * (periods // 2), dtype=float).shift(-idx).bfill()
    return pd.DataFrame(data)


def test_train_nearby_cwa_historical_model_trains_models(tmp_path):
    readiness = {"ready": True, "failed_reasons": [], "selected_station_ids": ["C0V890", "C0V490"]}

    result = train_nearby_cwa_historical_model(_dataset(), readiness, {}, tmp_path / "models", tmp_path / "reports")

    assert result["training_report"]["nearby_cwa_historical_model_trained"] is True
    assert "H1" in result["metrics"]["wind_speed"]
    assert "H1" in result["metrics"]["rain_probability"]
    assert "H1" in result["metrics"]["precipitation_amount"]
    assert (tmp_path / "models" / "precipitation_amount_H1.joblib").exists()
    assert (tmp_path / "reports" / "nearby_cwa_model_metrics.json").exists()


def test_train_nearby_cwa_historical_model_uses_target_algorithm_config(tmp_path):
    readiness = {"ready": True, "failed_reasons": [], "selected_station_ids": ["C0V890", "C0V490"]}
    config = {
        "nearby_cwa_historical_training": {
            "model_algorithms": {
                "wind_speed": {"primary_algorithm": "lightgbm"},
                "wind_gust": {"primary_algorithm": "random_forest"},
                "lightgbm": {"n_estimators": 5, "random_state": 42, "verbose": -1},
                "random_forest": {"n_estimators": 5, "random_state": 42, "min_samples_leaf": 1},
            }
        }
    }

    result = train_nearby_cwa_historical_model(_dataset(), readiness, config, tmp_path / "models", tmp_path / "reports")

    assert result["metrics"]["wind_speed"]["H1"]["algorithm"] == "lightgbm"
    assert result["metrics"]["wind_gust"]["H1"]["algorithm"] == "random_forest"
    assert result["metrics"]["wind_speed"]["H1"]["actual_estimator"] in {"LGBMRegressor", "GradientBoostingRegressor"}


def test_train_nearby_cwa_historical_model_skips_when_not_ready(tmp_path):
    result = train_nearby_cwa_historical_model(_dataset(10), {"ready": False, "failed_reasons": ["not ready"]}, {}, tmp_path / "models", tmp_path / "reports")

    assert result["training_report"]["nearby_cwa_historical_model_trained"] is False
