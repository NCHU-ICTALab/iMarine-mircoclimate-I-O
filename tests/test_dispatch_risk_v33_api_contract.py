import json

from kaohsiung_microclimate_lstm.src import predict as predict_module


def _config_text():
    return """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v3.3, model_version: kaohsiung_port_dispatch_risk_v3.3}
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
model_selection: {selection_engine_version: v3.3}
rain_probability: {cwa_pop_zero_is_valid_probability: true}
"""


def _write_reports(tmp_path):
    v32 = tmp_path / "results" / "dispatch_risk_v32"
    v32.mkdir(parents=True)
    (tmp_path / "results" / "dispatch_risk_v30").mkdir(parents=True)
    (tmp_path / "results" / "dispatch_risk_v30" / "dataset_readiness_report.json").write_text(json.dumps({"ready": False}), encoding="utf-8")
    (tmp_path / "results" / "dispatch_risk_v30" / "port_local_model_metrics.json").write_text(json.dumps({"port_local_model_trained": False}), encoding="utf-8")
    (v32 / "nearby_station_ranking_report.json").write_text(json.dumps({"selected_station_ids": ["C0V890"], "all_selected_stations_closer_than_467441": True}), encoding="utf-8")
    (v32 / "nearby_cwa_model_metrics.json").write_text(json.dumps({"nearby_cwa_historical_model_trained": True, "risk_level_evaluation": {"critical_under_warning_count": 0}}), encoding="utf-8")


def _patch_v32(monkeypatch):
    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v32",
        lambda **kwargs: {
            "model_version": "kaohsiung_port_dispatch_risk_v3.2",
            "prediction_mode": "port_local_postprocess",
            "station_priority_summary": {"port_local_station_count": 6},
            "nearby_cwa_historical_summary": {"model_accepted": True, "selected_station_ids": ["C0V890"], "all_selected_stations_closer_than_467441": True},
            "forecast_anchors": [{"label": f"H{i}", "rain": {"final_probability": 0.1}} for i in range(1, 5)],
            "trace": {"port_local_wind_station_count": 6, "rain_probability_preserved": True, "467441_used_as_core_station": False},
            "model_selection_summary": {},
        },
    )


def test_v33_api_contract_normal_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    _write_reports(tmp_path)
    _patch_v32(monkeypatch)

    result = predict_module.predict_dispatch_risk_v33(config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v3.3"
    assert result["prediction_mode"] == "port_local_postprocess"
    assert result["model_selection_summary"]["fallback_to_nearby_cwa_historical_model"] is False
    assert result["trace"]["467441_used_as_core_station"] is False
    assert result["trace"]["nearby_cwa_used_as_port_local_core"] is False
    assert result["model_selection_summary"]["evaluated_modes"]


def test_v33_api_contract_no_realtime_khwd_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    _write_reports(tmp_path)
    _patch_v32(monkeypatch)

    result = predict_module.predict_dispatch_risk_v33(config_path=str(cfg), project_root=tmp_path, no_realtime_khwd_mode=True)

    assert result["prediction_mode"] == "nearby_cwa_historical_model"
    assert result["model_selection_summary"]["fallback_to_nearby_cwa_historical_model"] is True
    assert result["trace"]["khwd_realtime_disabled_by_request"] is True
    assert result["trace"]["fallback_to_467441"] is False
