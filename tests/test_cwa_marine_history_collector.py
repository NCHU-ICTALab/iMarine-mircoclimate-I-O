from datetime import datetime, timedelta

from app.collectors.cwa_marine_history import parse_marine_payload
from app.config import Settings
from app.models import TAIPEI


def test_marine_payload_normalizes_tide_wave_current_fields():
    fetched_at = datetime(2026, 7, 2, 10, 0, tzinfo=TAIPEI)
    payload = {
        "Records": {
            "SeaSurfaceObs": {
                "Location": [
                    {
                        "Station": {"StationID": "COMC08"},
                        "StationObsTimes": {
                            "StationObsTime": [
                                {
                                    "DateTime": "2026-07-02T09:00:00+08:00",
                                    "WeatherElements": {
                                        "TideHeight": "0.21",
                                        "TideLevel": "漲潮",
                                        "WaveHeight": "0.3",
                                        "WavePeriod": "3.6",
                                        "Temperature": "28.9",
                                        "StationPressure": "1009.0",
                                        "PrimaryAnemometer": {
                                            "WindSpeed": "2.8",
                                            "WindDirection": "337.0",
                                            "MaximumWindSpeed": "3.9",
                                        },
                                        "SeaCurrents": {
                                            "Layer": [
                                                {
                                                    "LayerNumber": "1",
                                                    "CurrentDirection": "25",
                                                    "CurrentSpeed": "0.52",
                                                }
                                            ]
                                        },
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        }
    }

    observations = parse_marine_payload(
        payload,
        start=fetched_at - timedelta(hours=6),
        end=fetched_at,
        fetched_at=fetched_at,
        config=Settings(cwa_api_key="test", cwa_marine_station_ids="COMC08"),
    )

    assert len(observations) == 1
    obs = observations[0]
    assert obs.source == "cwa_marine_history"
    assert obs.device_type == "MARINE"
    assert obs.station_id == "COMC08"
    assert obs.station_name == "彌陀資料浮標"
    assert obs.location == "安平高雄沿海"
    assert obs.longitude == 120.1636
    assert obs.latitude == 22.7636
    assert obs.tide_level == 0.21
    assert obs.tide_level_unit == "m"
    assert obs.wave_height == 0.3
    assert obs.wave_period == 3.6
    assert obs.current_speed == 0.52
    assert obs.current_direction == 25.0
    assert obs.wind_speed == 2.8
    assert obs.wind_gust == 3.9
