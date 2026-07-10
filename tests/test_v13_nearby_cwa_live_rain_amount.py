import pandas as pd

from kaohsiung_microclimate_lstm.src.predict import (
    _condition_rain_amounts_on_probability,
    _select_precipitation_amount_observations,
    _station_ids_by_role,
)


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
