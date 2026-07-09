import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def _config_text() -> str:
    return """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v2.7, model_version: kaohsiung_port_dispatch_risk_v2.7}
forecast: {anchors: {H1: 30, H2: 60, H3: 90, H4: 120}}
spatial_scope: {mode: port_local, port_code: KHH, target_area_name: Kaohsiung Port, target_mode: port_area}
station_pool:
  enabled: true
  mode: port_local_priority
  station_pool_config: config/station_pool.yaml
  min_required_port_local_wind_stations: 2
station_priority: {enabled: true, enforce_port_local_first: true, allow_467441_as_core_station: false}
port_local_model: {enabled: false}
port_local_postprocess: {enabled: true}
fallback_baseline: {enabled: true, station_id: "467441", usage: fallback_only}
targets:
  precipitation: {variables: [precipitation_1hr], model_type: twostage_lstm}
  wind_speed_gust: {variables: [wind_speed, wind_gust], model_type: multitask_lstm}
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


def _pool_text() -> str:
    return """
station_pool_version: v2.7
station_pool_mode: port_local_priority
priority_groups:
  port_local_wind:
    priority: 1
    required_for_core_prediction: true
    stations:
      - {station_id: KHWD01, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
      - {station_id: KHWD04, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
  fallback_baseline:
    priority: 5
    stations:
      - {station_id: "467441", role: fallback_baseline, is_port_local: false, is_core_station: false, usage: fallback_only, enabled: true}
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
        "location_name": "Qianzhen District",
        "element_name": "PoP3h",
        "source_resolution": "3h",
        "anchor_pop": {"H3": 0.0, "H4": 0.0},
        "anchor_pop_quality": {
            label: {"available": True, "raw_value": "0", "normalized_value": 0.0, "parse_status": "ok", "alignment_status": "matched_forecast_period", "quality_status": "valid", "reason": None}
            for label in ["H1", "H2", "H3", "H4"]
        },
    }


def _write_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "station_pool.yaml").write_text(_pool_text(), encoding="utf-8")
    return cfg


def test_predict_dispatch_risk_v27_marks_fallback_when_khwd_missing(monkeypatch, tmp_path):
    cfg = _write_config(tmp_path)
    _patch_base_models(monkeypatch)
    fallback = pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]})

    result = predict_module.predict_dispatch_risk_v27(fallback_observations=fallback, cwa_forecast=_cwa_forecast(), config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.7"
    assert result["station_priority_summary"]["prediction_mode"] == "fallback_baseline"
    assert result["station_priority_summary"]["fallback_to_467441"] is True
    assert result["trace"]["467441_used_as_core_station"] is False
    assert result["trace"]["station_priority_policy"] == "port_local_first"
    assert result["forecast_anchors"][0]["port_local_postprocess"]["enabled"] is False


def test_predict_dispatch_risk_v27_uses_port_local_postprocess_when_khwd_available(monkeypatch, tmp_path):
    cfg = _write_config(tmp_path)
    _patch_base_models(monkeypatch)
    fallback = pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]})
    port_local = {
        "KHWD01": pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [11.0], "wind_gust": [14.0], "precipitation_1hr": [0.0]}),
        "KHWD04": pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [2.0], "precipitation_1hr": [1.0]}),
    }

    result = predict_module.predict_dispatch_risk_v27(
        port_local_observations=port_local,
        fallback_observations=fallback,
        cwa_forecast=_cwa_forecast(),
        config_path=str(cfg),
        project_root=tmp_path,
    )

    assert result["station_priority_summary"]["prediction_mode"] == "port_local_postprocess"
    assert result["station_priority_summary"]["using_port_local_station"] is True
    assert result["station_priority_summary"]["fallback_to_467441"] is False
    h1 = result["forecast_anchors"][0]
    assert h1["port_local_postprocess"]["port_local_wind_postprocess_applied"] is True
    assert h1["port_local_postprocess"]["port_local_gust_postprocess_applied"] is True
