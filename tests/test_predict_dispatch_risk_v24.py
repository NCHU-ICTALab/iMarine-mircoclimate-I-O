import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_predict_dispatch_risk_v24_smoke(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets:
  wind_speed_gust:
    variables: [wind_speed, wind_gust]
    model_type: multitask_lstm
project:
  model_version: kaohsiung_port_dispatch_risk_v2.4
forecast:
  anchors: {H1: 30, H2: 60, H3: 90, H4: 120}
spatial_scope:
  mode: port_local
  port_code: KHH
  target_area_name: Kaohsiung Port
cwa_pop:
  enabled: true
  allowed_in_model_input: false
  max_adjustment_weight: 0.2
  apply_anchors: [H3, H4]
wind_gust:
  uncertainty_buffer_mps: 1.2
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
  wind_gust_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}
reliability:
  wind_speed: high
  wind_gust: medium_high
  rain_probability: low_to_medium
""",
        encoding="utf-8",
    )

    def fake_rain(*args, **kwargs):
        return {
            "base_model_version": "rain_base",
            "anchors": [
                {"label": "H1", "offset_minutes": 30, "timestamp": "t1", "rain_probability": 0.2},
                {"label": "H2", "offset_minutes": 60, "timestamp": "t2", "rain_probability": 0.4},
                {"label": "H3", "offset_minutes": 90, "timestamp": "t3", "rain_probability": 0.6},
                {"label": "H4", "offset_minutes": 120, "timestamp": "t4", "rain_probability": 0.2},
            ],
            "cwa": {"available": True, "current": 0.8, "next": 0.9},
            "nearby_precip": {"available": True, "station_count": 3, "active_station_count": 1},
        }

    def fake_predict(*args, **kwargs):
        return {
            "model_version": "wind_base",
            "anchors": [
                {"label": "H1", "timestamp": "t1", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}},
                {"label": "H2", "timestamp": "t2", "wind_speed": {"value": 8.5}, "wind_gust": {"value": 10.0}},
                {"label": "H3", "timestamp": "t3", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}},
                {"label": "H4", "timestamp": "t4", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}},
            ],
        }

    monkeypatch.setattr(predict_module, "predict_rain_probability_v23", fake_rain)
    monkeypatch.setattr(predict_module, "predict", fake_predict)
    result = predict_module.predict_dispatch_risk_v24("467441", pd.DataFrame({"x": [1]}), config_path=str(cfg))
    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.4"
    assert len(result["forecast_anchors"]) == 4
    assert result["forecast_anchors"][1]["dispatch_risk_level"] == "watch"
    assert result["forecast_anchors"][2]["rain"]["level"] == "warning"
    assert result["data_availability"]["nearby_station_count"] == 3
    assert result["trace"]["port_local_scope"] is True
    assert result["trace"]["city_wide_forecast_as_target"] is False
    assert result["trace"]["train_inference_mismatch_prevented"] is True
    assert result["trace"]["cwa_pop_used_as_model_input"] is False
    assert result["trace"]["cwa_pop_used_as_postprocess_prior"] is True
