from kaohsiung_microclimate_lstm.src.model_selection.port_local_model_selector import select_dispatch_prediction_mode


def _config():
    return {
        "model_selection": {
            "preferred_order": ["port_local_model", "port_local_postprocess", "fallback_baseline"],
            "allow_fallback_to_port_local_postprocess": True,
            "allow_fallback_to_467441": True,
            "port_local_model_acceptance": {
                "wind_speed": {
                    "max_h1_mae_mps": 1.0,
                    "max_h2_mae_mps": 1.2,
                    "must_beat_persistence_h1": True,
                    "max_critical_under_warning_count": 0,
                },
                "wind_gust": {
                    "max_h1_mae_mps": 2.0,
                    "max_h2_mae_mps": 2.2,
                    "must_beat_persistence_h1": False,
                    "max_critical_under_warning_count": 0,
                },
                "rain_probability": {"required": False},
            },
        }
    }


def _metrics(wind_h1=0.5, critical=0):
    return {
        "port_local_model_trained": True,
        "wind_speed": {"H1": {"MAE": wind_h1, "beats_persistence": True}, "H2": {"MAE": 0.8}},
        "wind_gust": {"H1": {"MAE": 1.2, "beats_persistence": False}, "H2": {"MAE": 1.5}},
        "risk_level_evaluation": {"critical_under_warning_count": critical},
        "rain_probability": {"port_local_rain_model_trained": False},
    }


def test_selector_accepts_good_port_local_model():
    result = select_dispatch_prediction_mode(_metrics(), {"available": True}, {}, {"ready": True}, _config())

    assert result["selected_mode"] == "port_local_model"
    assert result["model_accepted"] is True


def test_selector_falls_back_to_postprocess_when_dataset_not_ready():
    result = select_dispatch_prediction_mode(None, {"available": True}, {}, {"ready": False, "failed_reasons": ["not enough data"]}, _config())

    assert result["selected_mode"] == "port_local_postprocess"
    assert result["fallback_to_port_local_postprocess"] is True


def test_selector_rejects_critical_under_warning():
    result = select_dispatch_prediction_mode(_metrics(critical=1), {"available": True}, {}, {"ready": True}, _config())

    assert result["selected_mode"] == "port_local_postprocess"
    assert any("critical_under_warning_count" in reason for reason in result["failed_reasons"])


def test_selector_uses_fallback_baseline_when_khwd_unavailable():
    result = select_dispatch_prediction_mode(None, {"available": False}, {}, {"ready": False}, _config())

    assert result["selected_mode"] == "fallback_baseline"
    assert result["fallback_to_467441"] is True
