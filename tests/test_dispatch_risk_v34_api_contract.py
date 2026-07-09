from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_v34_api_contract_required_fields(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v3.4, model_version: kaohsiung_port_dispatch_risk_v3.4}
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v33",
        lambda **kwargs: {
            "model_version": "kaohsiung_port_dispatch_risk_v3.3",
            "prediction_mode": "nearby_cwa_historical_model" if kwargs.get("no_realtime_khwd_mode") else "port_local_postprocess",
            "station_priority_summary": {"port_local_station_ids": ["KHWD01", "KHWD04"]},
            "nearby_cwa_historical_summary": {"model_accepted": True, "selected_station_ids": ["C0V890", "C0V490"]},
            "forecast_anchors": [{"label": "H1", "rain": {"final_probability": 0.2}}],
            "model_selection_summary": {"evaluated_modes": [{"mode": "port_local_postprocess"}]},
            "trace": {"selection_assertions": {}, "467441_used_as_core_station": False},
        },
    )
    monkeypatch.setattr(
        predict_module,
        "run_training_orchestration",
        lambda **kwargs: {
            "training_checked": True,
            "training_required": False,
            "training_skipped": True,
            "generated_at": "2026-07-09T13:30:00+08:00",
            "models": {"nearby_cwa_historical_model": {"trained": True, "available": True, "accepted": True, "selected_station_ids": ["C0V890", "C0V490"]}},
            "model_registry_summary": {"model_registry_used": True},
        },
    )

    result = predict_module.predict_dispatch_risk_v34(config_path=str(cfg), project_root=tmp_path, no_realtime_khwd_mode=True)

    for key in [
        "model_version",
        "prediction_mode",
        "model_selection_summary",
        "model_training_status",
        "model_registry_summary",
        "station_priority_summary",
        "current_station_usage",
        "station_display_rows",
        "nearby_cwa_historical_summary",
        "forecast_anchors",
        "data_availability",
        "trace",
    ]:
        assert key in result
    assert result["prediction_mode"] == "nearby_cwa_historical_model"
    assert result["current_station_usage"]["baseline_station_used_for_current_prediction"] is False
