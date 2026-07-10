import pandas as pd

from kaohsiung_microclimate_lstm.src.predict import _resolve_dispatch_anchor_time


def test_dispatch_anchor_uses_khwd_when_port_local_is_newer_than_467441():
    station_context = {
        "available_port_local_station_ids": ["KHWD01"],
        "station_frames": {
            "KHWD01": pd.DataFrame(
                {
                    "obs_time": ["2026-07-10T12:00:00+08:00"],
                    "wind_speed": [8.0],
                    "wind_gust": [14.0],
                }
            )
        },
    }
    fallback = pd.DataFrame({"obs_time": ["2026-07-05T23:00:00+08:00"], "wind_speed": [1.0]})

    result = _resolve_dispatch_anchor_time(
        prediction_mode="port_local_postprocess",
        station_context=station_context,
        fallback_observations=fallback,
        generated_at="2026-07-10T12:10:00+08:00",
    )

    assert result["anchor_time_source"] == "port_local_khwd"
    assert result["anchor_base_time"].isoformat() == "2026-07-10T12:00:00+08:00"
    assert result["anchor_time_staleness_minutes"] == 10


def test_dispatch_anchor_treats_port_local_model_as_khwd_source():
    station_context = {
        "available_port_local_station_ids": ["KHWD04"],
        "station_frames": {"KHWD04": pd.DataFrame({"obs_time": ["2026-07-10T13:00:00+08:00"]})},
    }

    result = _resolve_dispatch_anchor_time(
        prediction_mode="port_local_model",
        station_context=station_context,
        fallback_observations=pd.DataFrame({"obs_time": ["2026-07-05T23:00:00+08:00"]}),
        generated_at="2026-07-10T13:05:00+08:00",
    )

    assert result["anchor_time_source"] == "port_local_khwd"
    assert result["anchor_base_time"].isoformat() == "2026-07-10T13:00:00+08:00"
