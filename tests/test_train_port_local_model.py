import pandas as pd

from kaohsiung_microclimate_lstm.src.training.train_port_local_model import train_port_local_model


def _config(min_total=20, min_labels=10, min_days=1):
    return {
        "port_local_training": {
            "min_total_samples": min_total,
            "min_valid_label_samples_per_horizon": min_labels,
            "min_training_days": min_days,
            "max_feature_missing_ratio": 0.3,
            "max_label_missing_ratio": 0.3,
        },
        "port_local_model": {"train_wind_speed": True, "train_wind_gust": True},
    }


def _dataset(periods=120):
    times = pd.date_range("2026-07-01 00:00:00+08:00", periods=periods, freq="30min")
    speed = pd.Series(range(periods), dtype=float) / 10.0
    gust = speed + 2.0
    data = {
        "obs_time": times,
        "khwd_wind_speed_max": speed,
        "khwd_wind_speed_mean": speed - 0.2,
        "khwd_wind_gust_max": gust,
        "khwd_wind_gust_mean": gust - 0.2,
        "khwd_station_count": 2,
    }
    for idx, horizon in enumerate(["H1", "H2", "H3", "H4"], start=1):
        data[f"target_wind_speed_{horizon}"] = speed.shift(-idx).bfill()
        data[f"target_wind_gust_{horizon}"] = gust.shift(-idx).bfill()
    return pd.DataFrame(data)


def test_train_port_local_model_trains_wind_and_gust(tmp_path):
    result = train_port_local_model(_dataset(), _config(), tmp_path / "models", tmp_path / "reports")

    assert result["training_report"]["port_local_model_trained"] is True
    assert "H1" in result["metrics"]["wind_speed"]
    assert "MAE" in result["metrics"]["wind_gust"]["H1"]
    assert (tmp_path / "reports" / "port_local_model_metrics.json").exists()


def test_train_port_local_model_skips_insufficient_dataset(tmp_path):
    result = train_port_local_model(_dataset(4), _config(min_total=20), tmp_path / "models", tmp_path / "reports")

    assert result["training_report"]["port_local_model_trained"] is False
    assert result["metrics"]["port_local_model_trained"] is False
