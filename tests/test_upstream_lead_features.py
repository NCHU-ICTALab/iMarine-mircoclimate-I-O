import math

import pandas as pd

from kaohsiung_microclimate_lstm.src.data.upstream_lead_features import build_upstream_lead_features, resolve_season


def _zoning():
    return {
        "season_month_ranges": {
            "spring": [3, 4, 5],
            "summer": [6, 7, 8],
            "autumn": [9, 10, 11],
            "winter": [12, 1, 2],
        },
        "typhoon_season_months": [],
        "upstream_downstream_pairs": [
            {"season": "summer", "upstream_station_ids": ["C0V490"]},
            {"season": "winter", "upstream_station_ids": ["C0V810"]},
        ],
    }


def test_resolve_season_uses_configured_month_rules():
    zoning = _zoning()

    assert resolve_season("2026-03-01T00:00:00+08:00", zoning) == "spring"
    assert resolve_season("2026-07-01T00:00:00+08:00", zoning) == "summer"
    assert resolve_season("2026-10-01T00:00:00+08:00", zoning) == "autumn"
    assert resolve_season("2026-12-01T00:00:00+08:00", zoning) == "winter"


def test_resolve_season_gives_typhoon_months_priority():
    zoning = _zoning()
    zoning["typhoon_season_months"] = [7]

    assert resolve_season("2026-07-01T00:00:00+08:00", zoning) == "typhoon"


def test_build_upstream_lead_features_returns_nan_when_upstream_intersection_empty():
    raw = pd.DataFrame(
        {
            "obs_time": ["2026-07-01 00:00", "2026-07-01 00:00"],
            "station_id": ["C0V890", "C0V900"],
            "wind_speed": [3.0, 4.0],
            "wind_gust": [7.0, 8.0],
            "precipitation_1hr": [1.0, 2.0],
        }
    )

    features = build_upstream_lead_features(raw, _zoning(), ["C0V890", "C0V900"])

    assert features.loc[0, "upstream_subset_station_count"] == 0
    assert math.isnan(features.loc[0, "upstream_subset_wind_speed_mean"])
    assert math.isnan(features.loc[0, "upstream_subset_precipitation_1hr_max"])


def test_build_upstream_lead_features_aggregates_selected_upstream_subset_only():
    raw = pd.DataFrame(
        {
            "obs_time": ["2026-07-01 00:00", "2026-07-01 00:00"],
            "station_id": ["C0V490", "C0V890"],
            "wind_speed": [5.0, 20.0],
            "wind_gust": [9.0, 30.0],
            "precipitation_1hr": [2.5, 50.0],
        }
    )

    features = build_upstream_lead_features(raw, _zoning(), ["C0V490", "C0V890"])

    assert features.loc[0, "upstream_subset_station_count"] == 1
    assert features.loc[0, "upstream_subset_wind_speed_mean"] == 5.0
    assert features.loc[0, "upstream_subset_wind_gust_max"] == 9.0
    assert features.loc[0, "upstream_subset_precipitation_1hr_mean"] == 2.5
