import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def _config_text() -> str:
    return """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets:
  precipitation: {variables: [precipitation_1hr], model_type: twostage_lstm}
  wind_speed_gust: {variables: [wind_speed, wind_gust], model_type: multitask_lstm}
project: {version: v2.6, model_version: kaohsiung_port_dispatch_risk_v2.6}
forecast: {anchors: {H1: 30, H2: 60, H3: 90, H4: 120}}
target: {target_station_id: "467441", target_station_role: port_area_proxy}
spatial_scope: {mode: port_local, port_code: KHH, target_area_name: Kaohsiung Port}
station_pool: {enabled: true, mode: port_local}
multi_station_features: {enabled: true, mode: postprocess_only}
cwa_pop_quality: {enabled: true, distinguish_zero_and_missing: true}
cwa_pop_prior:
  enabled: true
  allowed_in_model_input: false
  max_weight: 0.2
  apply_anchors: [H3, H4]
  require_quality_available: true
  require_parse_status_ok: true
  resolution_weight_cap: {3h: 0.2, unknown: 0.05}
wind_speed: {thresholds_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}}
wind_gust: {uncertainty_buffer_mps: 1.2, thresholds_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}}
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
  wind_gust_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}
nearby_precip:
  enabled: true
  single_station_trigger_mm: 0.5
  single_station_min_probability: 0.70
  mean_trigger_mm: 2.0
  mean_min_probability: 0.85
  dry_suppression_probability: 0.15
reliability: {wind_speed: high, wind_gust: medium_high, rain_probability: low_to_medium, tide: reference_only}
risk_trigger:
  use_none_trigger_when_normal: true
  trigger_priority: [wind_gust, wind_speed, rain_probability, visibility, tide]
"""


def _patch_base_models(monkeypatch):
    monkeypatch.setattr(
        predict_module,
        "_run_raw_precipitation_lstm",
        lambda *args, **kwargs: ({"model_version": "rain_base"}, None, None, pd.DataFrame(), np.array([[0.1, 0.1, 0.1, 0.1]]), np.zeros(4)),
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


def _cwa_forecast():
    return {
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


def test_predict_dispatch_risk_v26_uses_multistation_postprocess(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    _patch_base_models(monkeypatch)
    target = pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]})
    frames = {
        "467441": target,
        "C4Q01": pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [11.0], "wind_gust": [14.0], "precipitation_1hr": [1.0]}),
        "C4Q02": pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [2.0], "wind_gust": [4.0], "precipitation_1hr": [0.0]}),
    }
    multi = {
        "target_station_id": "467441",
        "available_station_ids": ["467441", "C4Q01", "C4Q02"],
        "missing_station_ids": ["C4P01"],
        "station_frames": frames,
        "input_station_count": 3,
        "multi_station_input": True,
        "fallback_to_single_station": False,
        "fallback_reason": None,
    }

    result = predict_module.predict_dispatch_risk_v26("467441", target, multi_station_observations=multi, cwa_forecast=_cwa_forecast(), config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.6"
    assert result["input_station_summary"]["multi_station_input"] is True
    assert result["input_station_summary"]["fallback_to_single_station"] is False
    assert result["trace"]["multi_station_features_used_as_model_input"] is False
    assert result["trace"]["multi_station_features_used_as_postprocess"] is True
    h1 = result["forecast_anchors"][0]
    assert h1["rain"]["final_probability"] == 0.7
    assert h1["wind_speed"]["nearby_postprocess_applied"] is True
    assert h1["wind_gust"]["nearby_postprocess_applied"] is True
    assert h1["dispatch_risk_level"] == "high_risk"
    assert h1["risk_trigger_detail"]["primary_trigger"] == "rain_probability"


def test_predict_dispatch_risk_v26_marks_single_station_fallback(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    _patch_base_models(monkeypatch)
    target = pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]})
    multi = {
        "target_station_id": "467441",
        "available_station_ids": ["467441"],
        "missing_station_ids": ["C4Q01"],
        "station_frames": {"467441": target},
        "input_station_count": 1,
        "multi_station_input": False,
        "fallback_to_single_station": True,
        "fallback_reason": "Only target station data available.",
    }

    result = predict_module.predict_dispatch_risk_v26("467441", target, multi_station_observations=multi, cwa_forecast=_cwa_forecast(), config_path=str(cfg), project_root=tmp_path)

    assert result["input_station_summary"]["input_station_count"] == 1
    assert result["input_station_summary"]["fallback_to_single_station"] is True
    assert result["trace"]["multi_station_input"] is False
    assert result["trace"]["fallback_reason"] == "Only target station data available."
