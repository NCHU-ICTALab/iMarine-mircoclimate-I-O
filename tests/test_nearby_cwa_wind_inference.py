import json

import numpy as np
import pandas as pd

from kaohsiung_microclimate_lstm.src import predict as predict_module
from kaohsiung_microclimate_lstm.src.predict import _predict_nearby_wind_gusts, _predict_nearby_wind_speeds


class FakeModel:
    def __init__(self, value):
        self.value = value

    def predict(self, _x):
        return [self.value]


def _write_manifest(project):
    model_dir = project / "models" / "nearby_cwa_v32"
    model_dir.mkdir(parents=True)
    for name in ["wind_speed_H1", "wind_speed_H2", "wind_speed_H3", "wind_speed_H4", "wind_gust_H1", "wind_gust_H2", "wind_gust_H3", "wind_gust_H4"]:
        (model_dir / f"{name}.joblib").write_text("placeholder", encoding="utf-8")
    models = {name: {"model_path": f"models/nearby_cwa_v32/{name}.joblib"} for name in ["wind_speed_H1", "wind_speed_H2", "wind_speed_H3", "wind_speed_H4", "wind_gust_H1", "wind_gust_H2", "wind_gust_H3", "wind_gust_H4"]}
    (model_dir / "model_manifest.json").write_text(
        __import__("json").dumps({"models": models}),
        encoding="utf-8",
    )


def test_nearby_wind_speed_and_gust_predictions_load_manifest_and_features(tmp_path, monkeypatch):
    _write_manifest(tmp_path)

    def fake_load(path):
        name = path.stem
        value = 8.0 if name.startswith("wind_speed") else 12.0
        return {
            "model": FakeModel(value),
            "feature_columns": [
                "nearby_cwa_station_count",
                "nearby_cwa_wind_speed_max",
                "nearby_cwa_wind_gust_max",
                "nearby_cwa_wind_speed_max_lag1",
                "hour_sin",
            ],
            "fill_values": {"nearby_cwa_wind_speed_max_lag1": 3.0},
        }

    monkeypatch.setattr(predict_module.joblib, "load", fake_load)
    nearby = pd.DataFrame(
        {
            "station_id": ["C0V890", "C0V490"],
            "obs_time": pd.to_datetime(["2026-07-12T10:00:00+08:00", "2026-07-12T10:00:00+08:00"]),
            "wind_speed": [6.0, 7.0],
            "wind_gust": [10.0, 11.0],
            "wind_direction": [180.0, 190.0],
            "wind_gust_direction": [185.0, 195.0],
            "precipitation_1hr": [0.0, 0.0],
        }
    )

    speeds = _predict_nearby_wind_speeds(tmp_path, nearby, {})
    gusts = _predict_nearby_wind_gusts(tmp_path, nearby, {})

    assert speeds["available"] is True
    assert gusts["available"] is True
    assert speeds["source"] == "nearby_cwa_live_observations"
    assert all(np.isclose(value, 8.0) for value in speeds["values"].values())
    assert all(np.isclose(value, 12.0) for value in gusts["values"].values())


def test_nearby_wind_predictions_resolve_manifest_from_registry(tmp_path, monkeypatch):
    model_dir = tmp_path / "models" / "nearby_cwa_v34"
    model_dir.mkdir(parents=True)
    for name in ["wind_speed_H1", "wind_speed_H2", "wind_speed_H3", "wind_speed_H4"]:
        (model_dir / f"{name}.joblib").write_text("placeholder", encoding="utf-8")
    models = {name: {"model_path": f"models/nearby_cwa_v34/{name}.joblib"} for name in ["wind_speed_H1", "wind_speed_H2", "wind_speed_H3", "wind_speed_H4"]}
    manifest = model_dir / "model_manifest.json"
    manifest.write_text(__import__("json").dumps({"models": models}), encoding="utf-8")
    registry = tmp_path / "models" / "model_registry.json"
    registry.write_text(
        __import__("json").dumps({"models": {"nearby_cwa_historical_model": {"accepted": True, "manifest_path": str(manifest)}}}),
        encoding="utf-8",
    )

    loaded_paths = []

    def fake_load(path):
        loaded_paths.append(path)
        return {"model": FakeModel(9.0), "feature_columns": ["nearby_cwa_wind_speed_max"], "fill_values": {}}

    monkeypatch.setattr(predict_module.joblib, "load", fake_load)
    nearby = pd.DataFrame(
        {
            "station_id": ["C0V890"],
            "obs_time": pd.to_datetime(["2026-07-12T10:00:00+08:00"]),
            "wind_speed": [6.0],
            "wind_gust": [10.0],
        }
    )

    speeds = _predict_nearby_wind_speeds(tmp_path, nearby, {})

    assert speeds["available"] is True
    assert all(path.parent.name == "nearby_cwa_v34" for path in loaded_paths)


def test_nearby_wind_predictions_read_nested_v34_manifest_for_speed_and_gust(tmp_path, monkeypatch):
    model_dir = tmp_path / "models" / "nearby_cwa_v34"
    model_dir.mkdir(parents=True)
    models = {}
    for variable in ["wind_speed", "wind_gust"]:
        artifacts = {}
        for label in ["H1", "H2", "H3", "H4"]:
            name = f"{variable}_{label}"
            (model_dir / f"{name}.joblib").write_text("placeholder", encoding="utf-8")
            artifacts[name] = {"artifact_path": f"models/nearby_cwa_v34/{name}.joblib"}
        models[variable] = {"accepted": True, "artifacts": artifacts}
    manifest = model_dir / "model_manifest.json"
    manifest.write_text(json.dumps({"models": models}), encoding="utf-8")
    (tmp_path / "models" / "model_registry.json").write_text(
        json.dumps({"models": {"nearby_cwa_historical_model": {"accepted": True, "manifest_path": str(manifest)}}}),
        encoding="utf-8",
    )

    loaded_paths = []

    def fake_load(path):
        loaded_paths.append(path)
        value = 9.0 if path.stem.startswith("wind_speed") else 13.0
        return {
            "model": FakeModel(value),
            "feature_columns": ["nearby_cwa_wind_speed_max", "nearby_cwa_wind_gust_max"],
            "fill_values": {},
        }

    monkeypatch.setattr(predict_module.joblib, "load", fake_load)
    nearby = pd.DataFrame(
        {
            "station_id": ["C0V890"],
            "obs_time": pd.to_datetime(["2026-07-12T10:00:00+08:00"]),
            "wind_speed": [6.0],
            "wind_gust": [10.0],
        }
    )

    speeds = _predict_nearby_wind_speeds(tmp_path, nearby, {})
    gusts = _predict_nearby_wind_gusts(tmp_path, nearby, {})

    assert speeds["available"] is True
    assert gusts["available"] is True
    assert all(np.isclose(value, 9.0) for value in speeds["values"].values())
    assert all(np.isclose(value, 13.0) for value in gusts["values"].values())
    assert len(loaded_paths) == 8
    assert all(path.parent.name == "nearby_cwa_v34" for path in loaded_paths)
