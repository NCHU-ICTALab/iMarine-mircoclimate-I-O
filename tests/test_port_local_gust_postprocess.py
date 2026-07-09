from kaohsiung_microclimate_lstm.src.postprocess.port_local_gust_postprocess import apply_port_local_gust_postprocess


CONFIG = {"wind_gust": {"thresholds_mps": {"warning": 13.9, "high_risk": 17.2, "stop": 20.8}}}


def test_gust_postprocess_does_not_adjust_below_threshold():
    result = apply_port_local_gust_postprocess({"H1": "normal"}, {"features": {"khwd_wind_gust_max": 5.0}, "station_ids_used": ["KHWD01"]}, CONFIG)

    assert result["adjusted_predictions"]["H1"] == "normal"
    assert result["postprocess_detail"]["H1"]["applied"] is False


def test_gust_postprocess_adjusts_to_warning_and_high_risk():
    warning = apply_port_local_gust_postprocess({"H1": "normal"}, {"features": {"khwd_wind_gust_max": 14.0}, "station_ids_used": ["KHWD01"]}, CONFIG)
    high = apply_port_local_gust_postprocess({"H1": "normal"}, {"features": {"khwd_wind_gust_max": 18.0}, "station_ids_used": ["KHWD01"]}, CONFIG)

    assert warning["adjusted_predictions"]["H1"] == "warning"
    assert high["adjusted_predictions"]["H1"] == "high_risk"
    assert warning["postprocess_detail"]["H1"]["station_ids_used"] == ["KHWD01"]
