from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .config import Settings
from .models import Observation, UTC
from .parsing import cwa_weather_value, first_present, flatten_records, parse_time, to_float


logger = logging.getLogger(__name__)


class CwaCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self) -> list[Observation]:
        if not self.settings.cwa_api_key:
            logger.info("CWA_API_KEY is not configured; skipping CWA collector")
            return []

        url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
            f"{self.settings.cwa_data_id}"
        )
        params = {"Authorization": self.settings.cwa_api_key, "format": "JSON"}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        observations: list[Observation] = []
        for record in flatten_records(payload):
            station_name = str(
                first_present(record, ["StationName", "stationName", "locationName", "LocationName"])
                or ""
            )
            if self.settings.cwa_station_names and not any(
                target in station_name for target in self.settings.cwa_station_names
            ):
                continue
            station_id = str(
                first_present(record, ["StationId", "stationId", "StationID", "locationId", "LocationId"])
                or station_name
            )
            obs_time = parse_time(
                first_present(record, ["ObsTime", "obsTime", "time", "DateTime"])
                or (record.get("ObsTime") or {}).get("DateTime")
            )
            observations.append(
                Observation(
                    station_id=station_id,
                    station_name=station_name or station_id,
                    obs_time=obs_time,
                    source="B",
                    wind_speed=to_float(first_present(record, ["WindSpeed", "windSpeed"]) or cwa_weather_value(record, ["風速", "WindSpeed"])),
                    wind_gust=to_float(first_present(record, ["GustSpeed", "gustSpeed", "PeakGust"]) or cwa_weather_value(record, ["最大陣風", "GustSpeed"])),
                    wind_direction=to_float(first_present(record, ["WindDirection", "windDirection"]) or cwa_weather_value(record, ["風向", "WindDirection"])),
                    precipitation_10min=to_float(first_present(record, ["Precipitation10Min", "rainfall10min"]) or cwa_weather_value(record, ["10分鐘雨量"])),
                    precipitation_1hr=to_float(first_present(record, ["Precipitation", "precipitation", "Rainfall", "rainfall"]) or cwa_weather_value(record, ["降水量", "雨量"])),
                    visibility=to_float(first_present(record, ["Visibility", "visibility"]) or cwa_weather_value(record, ["能見度"])),
                    fetched_at=datetime.now(UTC),
                )
            )
        return observations
