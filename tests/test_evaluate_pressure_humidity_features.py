from kaohsiung_microclimate_lstm.src.tools.evaluate_pressure_humidity_features import _compare_metrics, _with_pressure_humidity_enabled


def test_with_pressure_humidity_enabled_does_not_mutate_original_config():
    config = {"nearby_cwa_historical_training": {"enable_pressure_humidity_features": False}}

    enabled = _with_pressure_humidity_enabled(config, True)

    assert config["nearby_cwa_historical_training"]["enable_pressure_humidity_features"] is False
    assert enabled["nearby_cwa_historical_training"]["enable_pressure_humidity_features"] is True


def test_compare_pressure_humidity_metrics_uses_auc_for_rain_probability():
    comparison = _compare_metrics(
        {"rain_probability": {"H1": {"AUC": 0.7, "CSI": 0.4}}},
        {"rain_probability": {"H1": {"AUC": 0.8, "CSI": 0.5}}},
    )

    assert comparison["rain_probability"]["H1"]["delta_AUC"] == 0.1
    assert comparison["rain_probability"]["H1"]["improved_by_primary_metric"] is True
