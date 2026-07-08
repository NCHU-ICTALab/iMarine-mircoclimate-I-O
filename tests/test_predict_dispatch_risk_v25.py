import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_predict_dispatch_risk_v25_smoke(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets:
  precipitation: {variables: [precipitation_1hr], model_type: twostage_lstm}
  wind_speed_gust: {variables: [wind_speed, wind_gust], model_type: multitask_lstm}
project: {model_version: kaohsiung_port_dispatch_risk_v2.5}
forecast: {anchors: {H1: 30, H2: 60, H3: 90, H4: 120}}
spatial_scope: {mode: port_local, port_code: KHH, target_area_name: Kaohsiung Port}
cwa_pop_prior:
  enabled: true
  allowed_in_model_input: false
  max_weight: 0.2
  apply_anchors: [H3, H4]
  resolution_weight_cap: {3h: 0.2, 6h: 0.15, 12h: 0.1, unknown: 0.05}
wind_gust: {uncertainty_buffer_mps: 1.2}
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
  wind_gust_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}
reliability: {wind_speed: high, wind_gust: medium_high, rain_probability: low_to_medium, tide: reference_only}
risk_trigger: {trigger_priority: [wind_gust, wind_speed, rain_probability, visibility, tide]}
""",
        encoding="utf-8",
    )

    def fake_raw(*args, **kwargs):
        return (
            {"model_version": "rain_base"},
            None,
            None,
            pd.DataFrame(index=[pd.Timestamp("2026-07-07T22:00:00+08:00")]),
            np.array([[0.2, 0.3, 0.4, 0.5]]),
            np.zeros(4),
        )

    def fake_nearby(*args, **kwargs):
        return {"available": True, "station_values_1hr": {"A": 0.0}, "max_1hr": 0.0, "mean_1hr": 0.0}

    def fake_predict(*args, **kwargs):
        return {
            "model_version": "wind_base",
            "anchors": [
                {"label": "H1", "timestamp": "t1", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}},
                {"label": "H2", "timestamp": "t2", "wind_speed": {"value": 8.5}, "wind_gust": {"value": 10.0}},
                {"label": "H3", "timestamp": "t3", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 12.9}},
                {"label": "H4", "timestamp": "t4", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}},
            ],
        }

    monkeypatch.setattr(predict_module, "_run_raw_precipitation_lstm", fake_raw)
    monkeypatch.setattr(predict_module, "_summarize_nearby_precipitation", fake_nearby)
    monkeypatch.setattr(predict_module, "predict", fake_predict)
    cwa = {"available": True, "dataset_id": "D", "location_name": "前鎮區", "source_resolution": "3h", "anchor_pop": {"H3": 0.8, "H4": 0.8}}
    result = predict_module.predict_dispatch_risk_v25("467441", pd.DataFrame({"x": [1]}), cwa_forecast=cwa, config_path=str(cfg))
    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.5"
    assert len(result["forecast_anchors"]) == 4
    assert "beaufort" in result["forecast_anchors"][0]["wind_speed"]
    assert result["forecast_anchors"][2]["wind_gust"]["buffer_applied"] is True
    assert result["forecast_anchors"][2]["rain"]["source_detail"]["cwa_prior_applied"] is True
    assert "risk_trigger_detail" in result["forecast_anchors"][0]
    assert "dispatch_action_level" in result["forecast_anchors"][0]
    assert result["trace"]["train_inference_mismatch_prevented"] is True
