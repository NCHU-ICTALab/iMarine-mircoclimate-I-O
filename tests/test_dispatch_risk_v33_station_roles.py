from kaohsiung_microclimate_lstm.src.predict import _build_v33_reports


def test_v33_station_role_report_keeps_non_khwd_sources_out_of_core():
    result = {"model_version": "kaohsiung_port_dispatch_risk_v3.3", "forecast_anchors": []}
    selection = {
        "selection_case_id": "CASE",
        "selected_mode": "nearby_cwa_historical_model",
        "fallback_chain": [],
        "evaluated_modes": [],
        "assertions": {"no_core_station_role_violation": True},
    }

    reports = _build_v33_reports(result, selection, {}, {})
    station = reports["station_role_violation_report.json"]

    assert station["violations_found"] is False
    assert station["checks"]["467441_used_as_core_station"] is False
    assert station["checks"]["nearby_cwa_used_as_port_local_core"] is False
    assert station["checks"]["cwa_pop_used_as_model_input"] is False
