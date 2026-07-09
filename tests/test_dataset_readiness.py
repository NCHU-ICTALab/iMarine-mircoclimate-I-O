import pandas as pd

from kaohsiung_microclimate_lstm.src.data.dataset_readiness import check_port_local_dataset_readiness


def _config(min_total=10, min_labels=5, min_days=1, max_missing=0.3):
    return {
        "port_local_training": {
            "min_total_samples": min_total,
            "min_valid_label_samples_per_horizon": min_labels,
            "min_training_days": min_days,
            "max_feature_missing_ratio": max_missing,
            "max_label_missing_ratio": max_missing,
        }
    }


def _dataset(periods=80):
    times = pd.date_range("2026-07-01 00:00:00+08:00", periods=periods, freq="30min")
    data = {
        "obs_time": times,
        "khwd_wind_speed_max": 3.0,
        "khwd_wind_gust_max": 5.0,
    }
    for horizon in ["H1", "H2", "H3", "H4"]:
        data[f"target_wind_speed_{horizon}"] = 3.5
        data[f"target_wind_gust_{horizon}"] = 5.5
    return pd.DataFrame(data)


def test_dataset_readiness_ready_true():
    result = check_port_local_dataset_readiness(_dataset(), _config())

    assert result["ready"] is True
    assert result["label_valid_count"]["H4"] == 80


def test_dataset_readiness_fails_when_short_and_missing_labels():
    dataset = _dataset(4)
    dataset["target_wind_speed_H4"] = None
    result = check_port_local_dataset_readiness(dataset, _config(min_total=10, min_labels=5, min_days=1))

    assert result["ready"] is False
    assert "sample_count below min_total_samples" in result["failed_reasons"]
    assert "H4 valid labels below threshold" in result["failed_reasons"]
