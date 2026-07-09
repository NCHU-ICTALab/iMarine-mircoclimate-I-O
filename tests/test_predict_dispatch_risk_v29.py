import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module


def _config_text() -> str:
    return """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v2.9, model_version: kaohsiung_port_dispatch_risk_v2.9}
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
port_local_wind_postprocess: {enabled: true, apply_anchors: [H1, H2], min_required_khwd_stations: 2}
port_local_rain_postprocess: {enabled: true, require_port_local_rain_data: false}
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
      - {station_id: KHWD01, type: wind, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
      - {station_id: KHWD04, type: wind, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
  fallback_baseline:
    priority: 5
    stations:
      - {station_id: "467441", type: weather, role: fallback_baseline, is_port_local: false, is_core_station: false, usage: fallback_only, enabled: true}
"""


def _patch_base_models(monkeypatch):
    monkeypatch.setattr(
        predict_module,
        "_run_raw_precipitation_lstm",
        lambda *args, **kwargs: ({"model_version": "rain_base"}, None, None, pd.DataFrame(), np.array([[0.31, 0.1, 0.1, 0.1]]), np.zeros(4)),
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


def _write_project(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_config_text(), encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "station_pool.yaml").write_text(_pool_text(), encoding="utf-8")
    raw = tmp_path / "data" / "raw" / "observed_hourly"
    raw.mkdir(parents=True)
    for station_id in ["KHWD01", "KHWD04"]:
        (raw / f"{station_id}.csv").write_text(
            "obs_time,station_id,wind_speed,wind_gust,wind_direction\n2026-07-08T10:00:00+08:00,"
            f"{station_id},11.0,14.0,180\n",
            encoding="utf-8",
        )
    return cfg


def test_predict_dispatch_risk_v29_outputs_reports_and_preserves_rain(monkeypatch, tmp_path):
    cfg = _write_project(tmp_path)
    _patch_base_models(monkeypatch)
    fallback = pd.DataFrame({"obs_time": ["2026-07-08T00:00:00+08:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]})

    result = predict_module.predict_dispatch_risk_v29(fallback_observations=fallback, cwa_forecast={"available": False, "anchor_pop": {}}, config_path=str(cfg), project_root=tmp_path)

    assert result["model_version"] == "kaohsiung_port_dispatch_risk_v2.9"
    assert result["station_priority_summary"]["prediction_mode"] == "port_local_postprocess"
    assert result["trace"]["rain_probability_preserved"] is True
    assert result["trace"]["467441_used_as_core_station"] is False
    assert result["forecast_anchors"][0]["rain"]["final_probability"] == 0.31
    assert result["forecast_anchors"][0]["wind_speed"]["port_local_postprocess"]["applied"] is True
    assert result["forecast_anchors"][0]["wind_gust"]["port_local_postprocess"]["applied"] is True
    assert (tmp_path / "results" / "dispatch_risk_v29" / "port_local_postprocess_report.json").exists()
    assert (tmp_path / "results" / "dispatch_risk_v29" / "rain_probability_report.json").exists()
