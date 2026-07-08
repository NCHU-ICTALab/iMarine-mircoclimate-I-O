import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_predict_dispatch_risk_v252_normal_trigger_none(monkeypatch, tmp_path):
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
project: {model_version: kaohsiung_port_dispatch_risk_v2.5.2}
forecast: {anchors: {H1: 30, H2: 60, H3: 90, H4: 120}}
spatial_scope: {mode: port_local, port_code: KHH, target_area_name: Kaohsiung Port}
cwa_pop_quality: {enabled: true, distinguish_zero_and_missing: true}
cwa_pop_prior:
  enabled: true
  allowed_in_model_input: false
  max_weight: 0.2
  apply_anchors: [H3, H4]
  require_quality_available: true
  require_parse_status_ok: true
  resolution_weight_cap: {3h: 0.2, unknown: 0.05}
wind_gust: {uncertainty_buffer_mps: 1.2}
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
  wind_gust_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}
reliability: {wind_speed: high, wind_gust: medium_high, rain_probability: low_to_medium, tide: reference_only}
risk_trigger:
  use_none_trigger_when_normal: true
  trigger_priority: [wind_gust, wind_speed, rain_probability, visibility, tide]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        predict_module,
        "_run_raw_precipitation_lstm",
        lambda *args, **kwargs: ({"model_version": "rain_base"}, None, None, pd.DataFrame(), np.array([[0.4, 0.2, 0.2, 0.2]]), np.zeros(4)),
    )
    monkeypatch.setattr(
        predict_module,
        "_summarize_nearby_precipitation",
        lambda *args, **kwargs: {"available": True, "station_values_1hr": {"A": 0.0}, "max_1hr": 0.0, "mean_1hr": 0.0},
    )
    monkeypatch.setattr(
        predict_module,
        "predict",
        lambda *args, **kwargs: {
            "model_version": "wind_base",
            "anchors": [
                {"label": f"H{i}", "timestamp": "t", "wind_speed": {"value": 1.0}, "wind_gust": {"value": 3.0}}
                for i in range(1, 5)
            ],
        },
    )
    cwa = {
        "available": True,
        "dataset_id": "D",
        "location_name": "前鎮區",
        "element_name": "PoP3h",
        "source_resolution": "3h",
        "anchor_pop": {"H3": 0.0, "H4": 0.0},
        "anchor_pop_quality": {
            label: {"available": True, "raw_value": "0", "normalized_value": 0.0, "parse_status": "ok", "alignment_status": "matched_forecast_period", "quality_status": "valid", "reason": None}
            for label in ["H1", "H2", "H3", "H4"]
        },
    }
    result = predict_module.predict_dispatch_risk_v252("467441", pd.DataFrame({"x": [1]}), cwa_forecast=cwa, config_path=str(cfg))
    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.5.2"
    assert result["forecast_anchors"][0]["risk_trigger_detail"]["primary_trigger"] == "rain_probability"
    for anchor in result["forecast_anchors"][1:]:
        assert anchor["dispatch_risk_level"] == "normal"
        assert anchor["risk_trigger_detail"]["primary_trigger"] == "none"
        assert anchor["dispatch_action_level"] == "normal_dispatch"
    assert result["trace"]["normal_state_primary_trigger_none"] is True
    assert result["trace"]["risk_trigger_semantics_patch_applied"] is True
