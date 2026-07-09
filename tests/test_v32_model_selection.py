from kaohsiung_microclimate_lstm.src.model_selection.port_local_model_selector import select_dispatch_prediction_mode_v32


def _config():
    return {
        "model_selection": {
            "preferred_order": ["port_local_model", "port_local_postprocess", "nearby_cwa_historical_model", "fallback_baseline"],
            "prefer_realtime_khwd_postprocess_over_nearby_historical": True,
            "allow_fallback_to_port_local_postprocess": True,
            "allow_fallback_to_467441": True,
            "port_local_model_acceptance": {"wind_speed": {}, "wind_gust": {}, "rain_probability": {"required": False}},
        },
        "nearby_cwa_historical_model_acceptance": {
            "wind_speed": {"max_h1_mae_mps": 1.3, "max_h2_mae_mps": 1.5, "must_beat_persistence_h1": True, "max_critical_under_warning_count": 0},
            "wind_gust": {"max_h1_mae_mps": 2.4, "max_h2_mae_mps": 2.8, "must_beat_persistence_h1": False, "max_critical_under_warning_count": 0},
            "rain_probability": {"max_brier_score": 0.25},
        },
    }


def _nearby_metrics():
    return {
        "nearby_cwa_historical_model_trained": True,
        "wind_speed": {"H1": {"MAE": 0.8, "beats_persistence": True}, "H2": {"MAE": 1.0}},
        "wind_gust": {"H1": {"MAE": 1.5}, "H2": {"MAE": 2.0}},
        "rain_probability": {"H1": {"Brier Score": 0.1}},
        "risk_level_evaluation": {"critical_under_warning_count": 0},
    }


def test_v32_selection_prefers_khwd_postprocess_when_available():
    result = select_dispatch_prediction_mode_v32(
        None,
        {"available": True},
        _nearby_metrics(),
        {},
        {"ready": False, "failed_reasons": ["khwd history short"]},
        {"ready": True},
        _config(),
    )

    assert result["selected_mode"] == "port_local_postprocess"
    assert result["fallback_to_nearby_cwa_historical_model"] is False


def test_v32_selection_uses_nearby_model_when_khwd_realtime_unavailable():
    result = select_dispatch_prediction_mode_v32(
        None,
        {"available": False},
        _nearby_metrics(),
        {},
        {"ready": False, "failed_reasons": ["khwd history short"]},
        {"ready": True},
        _config(),
    )

    assert result["selected_mode"] == "nearby_cwa_historical_model"
    assert result["fallback_to_467441"] is False
