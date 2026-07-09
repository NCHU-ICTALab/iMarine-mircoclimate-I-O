from kaohsiung_microclimate_lstm.src import predict as predict_module


def _fake_v33(**kwargs):
    return {
        "model_version": "kaohsiung_port_dispatch_risk_v3.3",
        "prediction_mode": "port_local_postprocess",
        "station_priority_summary": {"port_local_station_count": 2, "port_local_station_ids": ["KHWD01", "KHWD04"]},
        "nearby_cwa_historical_summary": {
            "model_accepted": True,
            "selected_station_ids": ["C0V890", "C0V490"],
            "all_selected_stations_closer_than_467441": True,
        },
        "forecast_anchors": [{"label": "H1", "rain": {"final_probability": 0.2}}],
        "model_selection_summary": {"selected_mode": "port_local_postprocess", "evaluated_modes": [{"mode": "port_local_postprocess"}]},
        "trace": {
            "selection_case_id": "KHWD_REALTIME_AVAILABLE_NEARBY_ACCEPTED",
            "selection_assertions": {},
            "467441_used_as_core_station": False,
            "nearby_cwa_used_as_port_local_core": False,
            "cwa_pop_used_as_model_input": False,
            "rain_probability_preserved": True,
        },
    }


def test_v34_api_returns_ui_station_usage(monkeypatch, tmp_path):
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
    monkeypatch.setattr(predict_module, "predict_dispatch_risk_v33", _fake_v33)
    monkeypatch.setattr(
        predict_module,
        "run_training_orchestration",
        lambda **kwargs: {
            "training_checked": True,
            "training_required": False,
            "training_skipped": True,
            "skip_reason": "Existing accepted nearby CWA historical model found.",
            "generated_at": "2026-07-09T13:30:00+08:00",
            "models": {
                "nearby_cwa_historical_model": {
                    "trained": True,
                    "available": True,
                    "accepted": True,
                    "artifact_version": "nearby_cwa_v34",
                    "selected_station_ids": ["C0V890", "C0V490"],
                },
                "port_local_model": {"trained": False, "available": False, "accepted": False},
            },
            "model_registry_summary": {"model_registry_used": True},
        },
    )

    result = predict_module.predict_dispatch_risk_v34(config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v3.4"
    assert "model_training_status" in result
    assert "current_station_usage" in result
    assert "station_display_rows" in result
    assert result["trace"]["selection_engine_version"] == "v3.4"
    assert result["trace"]["selection_assertions"]["station_usage_exported_to_ui"] is True
