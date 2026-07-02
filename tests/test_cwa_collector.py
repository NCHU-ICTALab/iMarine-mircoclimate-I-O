from datetime import datetime

from app.collectors.cwa import normalize_cwa_record
from app.config import Settings
from app.models import TAIPEI


def test_cwa_record_normalizes_weather_and_rain_fields():
    record = {
        "StationName": "高雄",
        "StationId": "467440",
        "ObsTime": {"DateTime": "2026-06-30T20:40:00+08:00"},
        "GeoInfo": {
            "Coordinates": [
                {
                    "StationLongitude": "120.3157",
                    "StationLatitude": "22.566",
                }
            ]
        },
        "WeatherElement": {
            "WindSpeed": "2.3",
            "WindDirection": "280",
            "AirTemperature": "29.5",
            "RelativeHumidity": "78",
            "AirPressure": "1005.1",
            "Visibility": "25000",
            "Past10Min": {"Precipitation": "0.5"},
            "Past1hr": {"Precipitation": "1.5"},
            "Past24hr": {"Precipitation": "12"},
        },
        "GustInfo": {"PeakGustSpeed": "5.5"},
    }
    config = Settings(cwa_api_key="test", cwa_station_names="高雄")

    obs = normalize_cwa_record(
        record,
        fetched_at=datetime(2026, 6, 30, 20, 45, tzinfo=TAIPEI),
        config=config,
    )

    assert obs is not None
    assert obs.source == "cwa"
    assert obs.device_type == "WEATHER"
    assert obs.wind_speed == 2.3
    assert obs.wind_gust == 5.5
    assert obs.precipitation_10min == 0.5
    assert obs.precipitation_1hr == 1.5
    assert obs.precipitation_24hr == 12.0
    assert obs.air_temperature == 29.5
    assert obs.relative_humidity == 78.0
    assert obs.air_pressure == 1005.1
    assert obs.visibility == 25000.0
    assert obs.stale is False
