import pandas as pd

from kaohsiung_microclimate_lstm.src.data.port_local_wind_aggregation import build_port_local_wind_features


def test_build_port_local_wind_features_aggregates_khwd_frames():
    frames = {
        "KHWD01": pd.DataFrame({"obs_time": ["2026-07-08T10:00:00+08:00"], "wind_speed": [3.0], "wind_gust": [5.0]}),
        "KHWD04": pd.DataFrame({"obs_time": ["2026-07-08T10:10:00+08:00"], "wind_speed": [4.0], "wind_gust": [8.0]}),
    }

    result = build_port_local_wind_features(frames, {"port_local_wind_postprocess": {"min_required_khwd_stations": 2}})

    assert result["features"]["khwd_wind_speed_max"] == 4.0
    assert result["features"]["khwd_wind_gust_max"] == 8.0
    assert result["features"]["khwd_station_count"] == 2
    assert result["quality_status"] == "ok"


def test_build_port_local_wind_features_handles_missing_khwd():
    result = build_port_local_wind_features({}, {})

    assert result["station_count"] == 0
    assert result["quality_status"] == "unavailable"
