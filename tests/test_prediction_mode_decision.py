from kaohsiung_microclimate_lstm.src.data.station_priority import decide_prediction_mode


def _config(port_model=False):
    return {
        "station_pool": {"min_required_port_local_wind_stations": 2},
        "port_local_model": {"enabled": port_model},
        "port_local_postprocess": {"enabled": True},
    }


def test_decide_prediction_mode_uses_port_local_model_when_available():
    decision = decide_prediction_mode(
        {"available_port_local_wind_station_ids": ["KHWD01", "KHWD04"], "available_port_local_station_ids": ["KHWD01", "KHWD04"]},
        {"metrics_ok": True},
        _config(port_model=True),
    )

    assert decision["prediction_mode"] == "port_local_model"
    assert decision["fallback_to_467441"] is False


def test_decide_prediction_mode_uses_postprocess_before_fallback():
    decision = decide_prediction_mode(
        {"available_port_local_wind_station_ids": ["KHWD01", "KHWD04"], "available_port_local_station_ids": ["KHWD01", "KHWD04"]},
        None,
        _config(port_model=False),
    )

    assert decision["prediction_mode"] == "port_local_postprocess"
    assert decision["model_retraining_required"] is True


def test_decide_prediction_mode_falls_back_when_port_local_missing():
    decision = decide_prediction_mode(
        {"available_port_local_wind_station_ids": [], "available_port_local_station_ids": []},
        None,
        _config(),
    )

    assert decision["prediction_mode"] == "fallback_baseline"
    assert decision["fallback_to_467441"] is True
    assert decision["fallback_reason"]
