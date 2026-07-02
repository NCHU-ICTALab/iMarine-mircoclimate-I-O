from datetime import datetime

from app.collectors.cwa_historyapi import extract_product_urls, parse_history_xml, redact_authorization
from app.config import Settings
from app.models import TAIPEI


def test_extract_product_urls_walks_metadata_payload():
    payload = {
        "dataset": {
            "resources": {
                "resource": {
                    "data": {
                        "time": [
                            {"ProductURL": "https://example.test/1"},
                            {"ProductURL": "https://example.test/2"},
                        ]
                    }
                }
            }
        }
    }

    assert extract_product_urls(payload) == ["https://example.test/1", "https://example.test/2"]


def test_redact_authorization_hides_cwa_key():
    url = "https://example.test/getData?Authorization=CWA-secret&format=JSON"

    assert redact_authorization(url) == "https://example.test/getData?Authorization=***&format=JSON"


def test_historyapi_xml_normalizes_weather_station():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
  <dataset>
    <Station>
      <StationName>高雄</StationName>
      <StationId>467441</StationId>
      <ObsTime><DateTime>2026-07-01T23:00:00+08:00</DateTime></ObsTime>
      <GeoInfo>
        <Coordinates>
          <CoordinateName>WGS84</CoordinateName>
          <StationLatitude>22.566</StationLatitude>
          <StationLongitude>120.3157</StationLongitude>
        </Coordinates>
        <StationAltitude>2.3</StationAltitude>
        <CountyName>高雄市</CountyName>
        <TownName>楠梓區</TownName>
      </GeoInfo>
      <WeatherElement>
        <Now><Precipitation>1.0</Precipitation></Now>
        <WindDirection>280.0</WindDirection>
        <WindSpeed>2.3</WindSpeed>
        <AirTemperature>29.5</AirTemperature>
        <RelativeHumidity>78</RelativeHumidity>
        <AirPressure>1005.1</AirPressure>
        <GustInfo>
          <PeakGustSpeed>5.5</PeakGustSpeed>
          <Occurred_at><WindDirection>290.0</WindDirection></Occurred_at>
        </GustInfo>
      </WeatherElement>
    </Station>
  </dataset>
</cwaopendata>
"""

    observations = parse_history_xml(
        xml,
        fetched_at=datetime(2026, 7, 1, 23, 5, tzinfo=TAIPEI),
        config=Settings(cwa_api_key="test", cwa_station_names="高雄", cwa_county_names="高雄市"),
    )

    assert len(observations) == 1
    obs = observations[0]
    assert obs.source == "cwa_historyapi"
    assert obs.device_type == "WEATHER"
    assert obs.station_id == "467441"
    assert obs.obs_time == datetime(2026, 7, 1, 23, 0, tzinfo=TAIPEI)
    assert obs.precipitation_1hr == 1.0
    assert obs.wind_speed == 2.3
    assert obs.wind_gust == 5.5
    assert obs.air_temperature == 29.5
    assert obs.relative_humidity == 78.0
    assert obs.air_pressure == 1005.1
