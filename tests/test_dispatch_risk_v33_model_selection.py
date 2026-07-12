from kaohsiung_microclimate_lstm.src.selection.model_selection_engine import select_prediction_mode


def _context():
    return {
        "port_local_model_available": False,
        "port_local_model_accepted": False,
        "dataset_ready": False,
        "port_local_model_trained": False,
        "port_local_model_critical_under_warning_count": 0,
        "khwd_realtime_available": True,
        "valid_khwd_station_count": 6,
        "no_realtime_khwd_mode": False,
        "nearby_cwa_historical_training_enabled": True,
        "nearby_cwa_historical_model_available": True,
        "nearby_cwa_historical_model_accepted": True,
        "all_nearby_cwa_stations_closer_than_467441": True,
        "nearby_cwa_critical_under_warning_count": 0,
        "fallback_baseline_available": True,
        "rain_probability_preserved": True,
        "cwa_pop_zero_is_valid_probability": True,
    }


def test_v33_selects_port_local_postprocess_when_khwd_realtime_available_even_if_nearby_accepted():
    result = select_prediction_mode(_context())

    assert result["selected_mode"] == "port_local_postprocess"
    assert result["fallback_to_nearby_cwa_historical_model"] is False
    assert result["fallback_to_467441"] is False


def test_v33_selection_reason_includes_port_local_model_failed_reasons():
    context = {**_context(), "port_local_failed_reasons": ["sample_count below min_total_samples"]}

    result = select_prediction_mode(context)

    assert result["selected_mode"] == "port_local_postprocess"
    assert "sample_count below min_total_samples" in result["selection_reason"]
    assert result["failed_reasons"] == ["sample_count below min_total_samples"]


def test_v33_selects_nearby_cwa_historical_model_when_khwd_unavailable_and_nearby_accepted():
    context = {**_context(), "khwd_realtime_available": False, "valid_khwd_station_count": 0, "no_realtime_khwd_mode": True}

    result = select_prediction_mode(context)

    assert result["selected_mode"] == "nearby_cwa_historical_model"
    assert result["fallback_to_nearby_cwa_historical_model"] is True
    assert result["fallback_to_467441"] is False


def test_v33_selects_fallback_baseline_only_when_khwd_and_nearby_unavailable():
    context = {
        **_context(),
        "khwd_realtime_available": False,
        "valid_khwd_station_count": 0,
        "no_realtime_khwd_mode": True,
        "nearby_cwa_historical_model_accepted": False,
    }

    result = select_prediction_mode(context)

    assert result["selected_mode"] == "fallback_baseline"
    assert result["fallback_to_nearby_cwa_historical_model"] is False
    assert result["fallback_to_467441"] is True


def test_v33_blocks_model_when_critical_under_warning_count_is_positive():
    context = {
        **_context(),
        "port_local_model_available": True,
        "port_local_model_accepted": True,
        "dataset_ready": True,
        "port_local_model_trained": True,
        "port_local_model_critical_under_warning_count": 1,
    }

    result = select_prediction_mode(context)

    assert result["selected_mode"] == "port_local_postprocess"
    assert "CRITICAL_UNDER_WARNING_COUNT_GT_0" in result["blocking_reasons"]["port_local_model"]
