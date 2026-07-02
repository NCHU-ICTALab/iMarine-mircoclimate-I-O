from datetime import datetime

from app.collectors.cwa_history import day_ranges, latest_codis_history_end, normalize_codis_row
from app.models import TAIPEI


def test_codis_history_row_normalizes_weather_fields():
    row = {
        "DataTime": "2026-07-01T08:00:00",
        "StationPressure": {"Instantaneous": 1008.5},
        "AirTemperature": {"Instantaneous": 29.1},
        "RelativeHumidity": {"Instantaneous": 81},
        "WindSpeed": {"Mean": 2.4},
        "WindDirection": {"Mean": 270},
        "PeakGust": {"Maximum": 5.2, "Direction": 290},
        "Precipitation": {"Accumulation": 1.5},
        "Visibility": {"AutoMean": 12.3},
    }

    obs = normalize_codis_row(
        row,
        {"station_id": "467441", "station_type": "cwb", "station_name": "高雄"},
        fetched_at=datetime(2026, 7, 1, 9, 0, tzinfo=TAIPEI),
    )

    assert obs is not None
    assert obs.source == "cwa_history"
    assert obs.station_id == "467441"
    assert obs.station_name == "高雄"
    assert obs.obs_time == datetime(2026, 7, 1, 8, 0, tzinfo=TAIPEI)
    assert obs.air_temperature == 29.1
    assert obs.relative_humidity == 81.0
    assert obs.air_pressure == 1008.5
    assert obs.wind_speed == 2.4
    assert obs.wind_direction == 270.0
    assert obs.wind_gust == 5.2
    assert obs.wind_gust_direction == 290.0
    assert obs.precipitation_1hr == 1.5
    assert obs.visibility == 12300.0


def test_day_ranges_splits_crossing_midnight():
    start = datetime(2026, 7, 1, 20, 0, tzinfo=TAIPEI)
    end = datetime(2026, 7, 2, 3, 59, 59, tzinfo=TAIPEI)

    ranges = day_ranges(start, end)

    assert ranges == [
        (start, datetime(2026, 7, 1, 23, 59, 59, tzinfo=TAIPEI)),
        (datetime(2026, 7, 2, 0, 0, tzinfo=TAIPEI), end),
    ]


def test_latest_codis_history_end_uses_previous_complete_day():
    now = datetime(2026, 7, 2, 17, 0, tzinfo=TAIPEI)

    assert latest_codis_history_end(now) == datetime(2026, 7, 1, 23, 59, 59, tzinfo=TAIPEI)
