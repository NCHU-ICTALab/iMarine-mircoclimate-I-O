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
