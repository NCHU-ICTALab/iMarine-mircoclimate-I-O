import json

from kaohsiung_microclimate_lstm.src import predict as predict_module


def _config_text():
    return """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v3.2, model_version: kaohsiung_port_dispatch_risk_v3.2}
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
forecast: {anchors: {H1: 30, H2: 60, H3: 90, H4: 120}}
model_selection:
  preferred_order: [port_local_model, port_local_postprocess, nearby_cwa_historical_model, fallback_baseline]
  prefer_realtime_khwd_postprocess_over_nearby_historical: true
  allow_fallback_to_port_local_postprocess: true
  allow_fallback_to_467441: true
  port_local_model_acceptance:
    wind_speed: {max_h1_mae_mps: 1.0, max_h2_mae_mps: 1.2, must_beat_persistence_h1: true, max_critical_under_warning_count: 0}
    wind_gust: {max_h1_mae_mps: 2.0, max_h2_mae_mps: 2.2, must_beat_persistence_h1: false, max_critical_under_warning_count: 0}
    rain_probability: {required: false}
nearby_cwa_historical_training:
  enabled: true
  baseline_station_id: "467441"
  priority_1_station_ids: [C0V890, C0V490]
nearby_cwa_historical_model_acceptance:
  wind_speed: {max_h1_mae_mps: 1.3, max_h2_mae_mps: 1.5, must_beat_persistence_h1: true, max_critical_under_warning_count: 0}
  wind_gust: {max_h1_mae_mps: 2.4, max_h2_mae_mps: 2.8, must_beat_persistence_h1: false, max_critical_under_warning_count: 0}
  rain_probability: {max_brier_score: 0.25}
rain_probability: {enabled: true, preserve_in_all_modes: true, allow_nearby_cwa_historical_rain_model: true}
cwa_pop_quality: {enabled: true}
"""


def test_predict_dispatch_risk_v32_adds_nearby_summary(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    v30 = tmp_path / "results" / "dispatch_risk_v30"
    v30.mkdir(parents=True)
    (v30 / "dataset_readiness_report.json").write_text(json.dumps({"ready": False, "failed_reasons": ["short"]}), encoding="utf-8")
    (v30 / "port_local_model_metrics.json").write_text(json.dumps({"port_local_model_trained": False}), encoding="utf-8")
    v32 = tmp_path / "results" / "dispatch_risk_v32"
    v32.mkdir(parents=True)
    (v32 / "nearby_station_ranking_report.json").write_text(
        json.dumps({"selected_station_ids": ["C0V890", "C0V490"], "all_selected_stations_closer_than_467441": True}),
        encoding="utf-8",
    )
    (v32 / "nearby_cwa_readiness_report.json").write_text(json.dumps({"ready": True, "selected_station_ids": ["C0V890", "C0V490"]}), encoding="utf-8")
    (v32 / "nearby_cwa_model_metrics.json").write_text(
        json.dumps(
            {
                "nearby_cwa_historical_model_trained": True,
                "wind_speed": {"H1": {"MAE": 0.8, "beats_persistence": True}, "H2": {"MAE": 1.0}},
                "wind_gust": {"H1": {"MAE": 1.5}, "H2": {"MAE": 2.0}},
                "rain_probability": {"H1": {"Brier Score": 0.1}},
                "risk_level_evaluation": {"critical_under_warning_count": 0},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v30",
        lambda **kwargs: {
            "model_version": "kaohsiung_port_dispatch_risk_v3.0",
            "prediction_mode": "port_local_postprocess",
            "station_priority_summary": {"using_port_local_station": True, "prediction_mode": "port_local_postprocess"},
            "trace": {"port_local_wind_station_count": 2, "rain_probability_preserved": True, "467441_used_as_core_station": False},
            "forecast_anchors": [],
            "model_selection_summary": {"selected_mode": "port_local_postprocess"},
        },
    )

    result = predict_module.predict_dispatch_risk_v32(config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v3.2"
    assert result["model_selection_summary"]["selected_mode"] == "port_local_postprocess"
    assert result["nearby_cwa_historical_summary"]["model_accepted"] is True
    assert result["trace"]["nearby_cwa_used_as_port_local_core"] is False
    assert result["trace"]["467441_used_as_core_station"] is False
    assert (v32 / "prediction_samples.json").exists()
