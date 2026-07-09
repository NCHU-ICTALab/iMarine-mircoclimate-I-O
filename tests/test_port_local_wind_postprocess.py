from kaohsiung_microclimate_lstm.src.postprocess.port_local_wind_postprocess import apply_port_local_wind_postprocess


CONFIG = {"wind_speed": {"thresholds_mps": {"warning": 10.8, "high_risk": 13.9, "stop": 17.2}}}


def test_wind_postprocess_does_not_adjust_below_threshold():
    result = apply_port_local_wind_postprocess({"H1": "normal"}, {"features": {"khwd_wind_speed_max": 5.0}, "station_ids_used": ["KHWD01"]}, CONFIG)

    assert result["adjusted_predictions"]["H1"] == "normal"
    assert result["postprocess_detail"]["H1"]["applied"] is False


def test_wind_postprocess_adjusts_to_warning_and_high_risk():
    warning = apply_port_local_wind_postprocess({"H1": "normal"}, {"features": {"khwd_wind_speed_max": 11.0}, "station_ids_used": ["KHWD01"]}, CONFIG)
    high = apply_port_local_wind_postprocess({"H1": "normal"}, {"features": {"khwd_wind_speed_max": 14.0}, "station_ids_used": ["KHWD01"]}, CONFIG)

    assert warning["adjusted_predictions"]["H1"] == "warning"
    assert high["adjusted_predictions"]["H1"] == "high_risk"
    assert warning["postprocess_detail"]["H1"]["station_ids_used"] == ["KHWD01"]
