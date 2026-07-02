from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .config import Settings
from .models import Observation, UTC
from .parsing import first_present, flatten_records, parse_time, to_float


logger = logging.getLogger(__name__)


class TwPortCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self) -> list[Observation]:
        if not self.settings.twport_api_url:
            logger.info("TWPORT_API_URL is not configured; skipping TWPort collector")
            return []

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(self.settings.twport_api_url)
            response.raise_for_status()
            payload = response.json()

        observations: list[Observation] = []
        for record in flatten_records(payload):
            station_name = str(
                first_present(record, ["station_name", "stationName", "name", "Name", "測站名稱"])
                or ""
            )
            if self.settings.twport_station_names and not any(
                target in station_name for target in self.settings.twport_station_names
            ):
                continue
            station_id = str(
                first_present(record, ["station_id", "stationId", "id", "Id", "測站代碼"])
                or station_name
            )
            observations.append(
                Observation(
                    station_id=station_id,
                    station_name=station_name or station_id,
                    obs_time=parse_time(first_present(record, ["obs_time", "obsTime", "time", "Time", "觀測時間"])),
                    source="A",
                    wind_speed=to_float(first_present(record, ["wind_speed", "windSpeed", "WindSpeed", "風速"])),
                    wind_gust=to_float(first_present(record, ["wind_gust", "gust", "GustSpeed", "陣風"])),
                    wind_direction=to_float(first_present(record, ["wind_direction", "windDirection", "WindDirection", "風向"])),
                    precipitation_10min=to_float(first_present(record, ["precipitation_10min", "rain10min", "Rain10Min", "十分鐘雨量"])),
                    precipitation_1hr=to_float(first_present(record, ["precipitation_1hr", "rain1hr", "Rain1Hr", "一小時雨量"])),
                    visibility=to_float(first_present(record, ["visibility", "Visibility", "能見度"])),
                    tide_level=to_float(first_present(record, ["tide_level", "tideLevel", "TideLevel", "潮位"])),
                    wave_height=to_float(first_present(record, ["wave_height", "waveHeight", "WaveHeight", "浪高"])),
                    fetched_at=datetime.now(UTC),
                )
            )
        return observations
