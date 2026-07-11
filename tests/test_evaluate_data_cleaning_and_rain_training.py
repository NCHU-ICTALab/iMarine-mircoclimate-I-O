from kaohsiung_microclimate_lstm.src.tools.evaluate_data_cleaning_and_rain_training import _precipitation_improved, _rain_training_config


def test_rain_training_config_does_not_mutate_original():
    config = {"nearby_cwa_historical_training": {"precipitation_amount_training": {"train_on_rain_events_only": False}}}

    updated = _rain_training_config(config, train_on_rain_events_only=True, log1p_target=True)

    assert config["nearby_cwa_historical_training"]["precipitation_amount_training"]["train_on_rain_events_only"] is False
    assert updated["nearby_cwa_historical_training"]["precipitation_amount_training"]["train_on_rain_events_only"] is True
    assert updated["nearby_cwa_historical_training"]["precipitation_amount_training"]["log1p_target"] is True


def test_precipitation_improved_uses_h1_mae():
    previous = {"precipitation_amount": {"H1": {"MAE": 1.0}}}
    current = {"precipitation_amount": {"H1": {"MAE": 0.9}}}

    assert _precipitation_improved(previous, current) is True
