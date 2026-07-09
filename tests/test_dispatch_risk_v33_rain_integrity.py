from kaohsiung_microclimate_lstm.src.predict import _build_v33_reports


def test_v33_rain_integrity_report_requires_rain_in_all_anchors():
    result = {
        "model_version": "kaohsiung_port_dispatch_risk_v3.3",
        "forecast_anchors": [{"label": "H1", "rain": {"final_probability": 0.1}}, {"label": "H2"}],
    }
    selection = {
        "selection_case_id": "CASE",
        "selected_mode": "port_local_postprocess",
        "fallback_chain": [],
        "evaluated_modes": [],
        "assertions": {"rain_probability_preserved_in_all_anchors": False},
    }

    reports = _build_v33_reports(result, selection, {}, {"rain_probability": {"cwa_pop_zero_is_valid_probability": True}})

    rain = reports["rain_probability_integrity_report.json"]
    assert rain["rain_probability_preserved"] is False
    assert rain["missing_rain_anchors"] == ["H2"]
    assert rain["cwa_pop_used_as_model_input"] is False
