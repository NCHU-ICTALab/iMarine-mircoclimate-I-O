from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
UTC = timezone.utc


@dataclass
class Observation:
    station_id: str
    station_name: str
    obs_time: datetime
    source: str
    wind_speed: float | None = None
    wind_gust: float | None = None
    wind_direction: float | None = None
    precipitation_10min: float | None = None
    precipitation_1hr: float | None = None
    visibility: float | None = None
    tide_level: float | None = None
    wave_height: float | None = None
    is_forecast: bool = False
    confidence: str = "high"
    fetched_at: datetime | None = None

    def normalized(self) -> "Observation":
        obs_time = ensure_utc(self.obs_time)
        fetched_at = ensure_utc(self.fetched_at or datetime.now(UTC))
        return Observation(**{**asdict(self), "obs_time": obs_time, "fetched_at": fetched_at})


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=TAIPEI)
    return value.astimezone(UTC)


def to_taipei_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_utc(value).astimezone(TAIPEI).isoformat()


def observation_to_api_dict(observation: Observation, stale: bool = False) -> dict[str, Any]:
    return {
        "station_id": observation.station_id,
        "station_name": observation.station_name,
        "obs_time": to_taipei_iso(observation.obs_time),
        "source": observation.source,
        "wind_speed": observation.wind_speed,
        "wind_gust": observation.wind_gust,
        "wind_direction": observation.wind_direction,
        "precipitation_10min": observation.precipitation_10min,
        "precipitation_1hr": observation.precipitation_1hr,
        "visibility": observation.visibility,
        "tide_level": observation.tide_level,
        "wave_height": observation.wave_height,
        "is_forecast": observation.is_forecast,
        "confidence": observation.confidence,
        "stale": stale,
        "fetched_at": to_taipei_iso(observation.fetched_at),
    }
