from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass
class TwPortObservation:
    source: str
    port_code: str | None
    station_id: str
    station_name: str
    location: str | None
    device_type: str
    obs_time: datetime
    longitude: float | None = None
    latitude: float | None = None
    elevation: float | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None
    wind_direction: float | None = None
    wind_gust_direction: float | None = None
    precipitation_10min: float | None = None
    precipitation_1hr: float | None = None
    precipitation_24hr: float | None = None
    air_temperature: float | None = None
    relative_humidity: float | None = None
    air_pressure: float | None = None
    visibility: float | None = None
    tide_level: float | None = None
    tide_level_unit: str | None = "raw"
    wave_height: float | None = None
    wave_period: float | None = None
    wave_max_height: float | None = None
    current_speed: float | None = None
    current_direction: float | None = None
    raw_data: dict[str, Any] | None = None
    raw_last_data_str: str | None = None
    is_forecast: bool = False
    confidence: str = "high"
    stale: bool = False
    fetched_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["obs_time"] = self.obs_time.astimezone(TAIPEI).isoformat()
        if self.fetched_at:
            data["fetched_at"] = self.fetched_at.astimezone(TAIPEI).isoformat()
        return data
