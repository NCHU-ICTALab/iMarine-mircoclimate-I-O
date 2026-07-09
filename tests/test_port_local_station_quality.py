import pandas as pd

from kaohsiung_microclimate_lstm.src.data.port_local_station_quality import validate_port_local_station_frame


def test_valid_khwd_frame_quality_ok():
    df = pd.DataFrame(
        {
            "obs_time": ["2026-07-08T10:00:00+08:00"],
            "wind_speed": [5.0],
            "wind_gust": [8.0],
            "wind_direction": [180.0],
        }
    )

    report = validate_port_local_station_frame(df, "KHWD01", "wind")

    assert report["valid"] is True
    assert report["quality_status"] == "ok"


def test_wind_out_of_range_is_degraded():
    df = pd.DataFrame(
        {
            "obs_time": ["2026-07-08T10:00:00+08:00"],
            "wind_speed": [-1.0],
            "wind_gust": [120.0],
            "wind_direction": [361.0],
        }
    )

    report = validate_port_local_station_frame(df, "KHWD01", "wind")

    assert report["quality_status"] == "degraded"
    assert report["out_of_range_count"]["wind_speed"] == 1
    assert report["out_of_range_count"]["wind_gust"] == 1
    assert report["out_of_range_count"]["wind_direction"] == 1


def test_empty_frame_is_unavailable():
    report = validate_port_local_station_frame(pd.DataFrame(), "KHWD01", "wind")

    assert report["valid"] is False
    assert report["quality_status"] == "unavailable"
