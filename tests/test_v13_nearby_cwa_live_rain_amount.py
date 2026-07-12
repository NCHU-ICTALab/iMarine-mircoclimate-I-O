import json

import pandas as pd
import numpy as np

from kaohsiung_microclimate_lstm.src.predict import (
    _condition_rain_amounts_on_probability,
    _predict_nearby_precipitation_amounts,
    _select_precipitation_amount_observations,
    _station_ids_by_role,
)
from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_nearby_cwa_live_role_ids_are_selected_for_rain_amount():
    station_pool = {
        "priority_groups": {
            "port_local_wind": {
                "priority": 1,
                "role": "port_local_wind_station",
                "stations": [{"station_id": "KHWD01", "role": "port_local_wind_station"}],
            },
            "nearby_cwa_live": {
                "priority": 7,
                "role": "nearby_cwa_live_reference",
                "stations": [{"station_id": "C0V890", "role": "nearby_cwa_live_reference"}],
            },
        }
    }

    assert _station_ids_by_role(station_pool, "nearby_cwa_live_reference") == ["C0V890"]


def test_precipitation_amount_prefers_nearby_cwa_live_over_fallback():
    nearby = pd.DataFrame({"station_id": ["C0V890"], "precipitation_1hr": [2.0]})
    fallback = pd.DataFrame({"station_id": ["467441"], "precipitation_1hr": [99.0]})

    selected, source = _select_precipitation_amount_observations(nearby, fallback)

    assert source == "nearby_cwa_live_observations"
    assert float(selected["precipitation_1hr"].iloc[0]) == 2.0


def test_rain_amount_is_zero_when_event_probability_below_threshold():
    conditioned = _condition_rain_amounts_on_probability(
        {"H1": 12.0, "H2": 5.0},
        {"H1": 0.2, "H2": 0.8},
        {"rain_amount_regression": {"inference_probability_threshold": 0.5}},
    )

    assert conditioned["H1"] == 0.0
    assert conditioned["H2"] == 5.0


def test_precipitation_amount_prediction_restores_log1p_transform(tmp_path, monkeypatch):
    class FakeModel:
        def predict(self, _x):
            return [np.log1p(5.0)]

    project = tmp_path
    model_dir = project / "models" / "nearby_cwa_v32"
    model_dir.mkdir(parents=True)
    (model_dir / "fake.joblib").write_text("placeholder", encoding="utf-8")
    (model_dir / "model_manifest.json").write_text(
        '{"models": {"precipitation_amount_H1": {"model_path": "models/nearby_cwa_v32/fake.joblib"}}}',
        encoding="utf-8",
    )

    def fake_load(_path):
        return {
            "model": FakeModel(),
            "feature_columns": ["nearby_cwa_precipitation_1hr_max"],
            "fill_values": {},
            "target_transform": "log1p",
        }

    monkeypatch.setattr(predict_module.joblib, "load", fake_load)
    nearby = pd.DataFrame({"station_id": ["C0V890"], "obs_time": ["2026-07-01 00:00"], "precipitation_1hr": [2.0]})

    result = _predict_nearby_precipitation_amounts(project, nearby)

    assert round(result["amounts"]["H1"], 3) == 5.0


def test_precipitation_amount_prediction_reads_nested_v34_manifest(tmp_path, monkeypatch):
    class FakeModel:
        def predict(self, _x):
            return [4.2]

    model_dir = tmp_path / "models" / "nearby_cwa_v34"
    model_dir.mkdir(parents=True)
    for label in ["H1", "H2", "H3", "H4"]:
        (model_dir / f"precipitation_amount_{label}.joblib").write_text("placeholder", encoding="utf-8")
    manifest = model_dir / "model_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "models": {
                    "precipitation_amount": {
                        "accepted": True,
                        "artifacts": {
                            f"precipitation_amount_{label}": {
                                "artifact_path": f"models/nearby_cwa_v34/precipitation_amount_{label}.joblib"
                            }
                            for label in ["H1", "H2", "H3", "H4"]
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    registry = tmp_path / "models" / "model_registry.json"
    registry.write_text(
        json.dumps({"models": {"nearby_cwa_historical_model": {"accepted": True, "manifest_path": str(manifest)}}}),
        encoding="utf-8",
    )

    loaded_paths = []

    def fake_load(path):
        loaded_paths.append(path)
        return {
            "model": FakeModel(),
            "feature_columns": ["nearby_cwa_precipitation_1hr_max"],
            "fill_values": {},
        }

    monkeypatch.setattr(predict_module.joblib, "load", fake_load)
    nearby = pd.DataFrame(
        {"station_id": ["C0V890"], "obs_time": ["2026-07-01 00:00"], "precipitation_1hr": [2.0]}
    )

    result = _predict_nearby_precipitation_amounts(tmp_path, nearby)

    assert all(value == 4.2 for value in result["amounts"].values())
    assert all(path.parent.name == "nearby_cwa_v34" for path in loaded_paths)


def test_predict_dispatch_risk_v35_keeps_high_probability_rain_amount_non_null_with_nested_manifest(tmp_path, monkeypatch):
    class FakeModel:
        def predict(self, _x):
            return [6.5]

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
project: {version: v3.5, model_version: kaohsiung_port_dispatch_risk_v1.3}
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets:
  precipitation: {variables: [precipitation_1hr]}
  wind_speed_gust: {variables: [wind_speed, wind_gust]}
rain_amount_regression: {inference_probability_threshold: 0.5}
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
  wind_gust_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}
wind_speed: {thresholds_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}}
wind_gust: {uncertainty_buffer_mps: 1.2, thresholds_mps: {watch: 10.8, warning: 13.9, high_risk: 17.2, stop: 20.8}}
rain_postprocess: {cwa_pop3h: {fallback_location: 前鎮區}}
cwa_open_data: {enabled: false}
reliability: {wind_speed: high, wind_gust: medium_high, rain_probability: low_to_medium, tide: reference_only}
risk_trigger: {use_none_trigger_when_normal: true, trigger_priority: [wind_gust, wind_speed, rain_probability, visibility, tide]}
""",
        encoding="utf-8",
    )
    model_dir = tmp_path / "models" / "nearby_cwa_v34"
    model_dir.mkdir(parents=True)
    artifacts = {}
    for label in ["H1", "H2", "H3", "H4"]:
        (model_dir / f"precipitation_amount_{label}.joblib").write_text("placeholder", encoding="utf-8")
        artifacts[f"precipitation_amount_{label}"] = {
            "artifact_path": f"models/nearby_cwa_v34/precipitation_amount_{label}.joblib"
        }
    manifest = model_dir / "model_manifest.json"
    manifest.write_text(json.dumps({"models": {"precipitation_amount": {"accepted": True, "artifacts": artifacts}}}), encoding="utf-8")
    (tmp_path / "models" / "model_registry.json").write_text(
        json.dumps({"models": {"nearby_cwa_historical_model": {"accepted": True, "manifest_path": str(manifest)}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        predict_module,
        "_run_raw_precipitation_lstm",
        lambda *args, **kwargs: (
            {"model_version": "rain_base"},
            None,
            None,
            pd.DataFrame(),
            np.array([[0.85, 0.85, 0.85, 0.85]]),
            np.zeros(4),
        ),
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
    monkeypatch.setattr(
        predict_module.joblib,
        "load",
        lambda _path: {
            "model": FakeModel(),
            "feature_columns": ["nearby_cwa_precipitation_1hr_max"],
            "fill_values": {},
        },
    )
    monkeypatch.setattr(
        predict_module,
        "fetch_pop3h",
        lambda *args, **kwargs: {"available": False, "source": "test"},
    )
    nearby = pd.DataFrame(
        {
            "station_id": ["C0V890"],
            "obs_time": ["2026-07-01 00:00"],
            "precipitation_1hr": [2.0],
            "wind_speed": [3.0],
            "wind_gust": [5.0],
        }
    )
    fallback = pd.DataFrame(
        {"obs_time": ["2026-07-01 00:00"], "wind_speed": [1.0], "wind_gust": [3.0], "precipitation_1hr": [0.0]}
    )

    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v34",
        lambda **kwargs: predict_module.predict_dispatch_risk_v25(
            "467441",
            fallback,
            nearby_observations=nearby,
            cwa_forecast={"available": False, "anchor_pop": {}},
            config_path=str(cfg),
            project_root=tmp_path,
        ),
    )

    result = predict_module.predict_dispatch_risk_v35(config_path=str(cfg), project_root=tmp_path)

    for anchor in result["forecast_anchors"]:
        assert anchor["rain"]["final_probability"] == 0.85
        assert anchor["rain"]["predicted_amount_mm"] == 6.5
        assert anchor["rain"]["amount_level"] is not None
