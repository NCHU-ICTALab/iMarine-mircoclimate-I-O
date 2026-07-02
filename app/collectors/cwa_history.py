from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import Settings, settings
from app.models import TAIPEI, TwPortObservation


logger = logging.getLogger(__name__)

CODIS_STATION_URL = "https://codis.cwa.gov.tw/api/station"
ALLOWED_HISTORY_HOURS = (6, 12, 24, 48)


async def collect_history(hours: int = 24, config: Settings = settings) -> list[TwPortObservation]:
    if hours not in ALLOWED_HISTORY_HOURS:
        raise ValueError(f"hours must be one of {ALLOWED_HISTORY_HOURS}")

    end = latest_codis_history_end()
    start = end.replace(minute=0, second=0) - timedelta(hours=hours - 1)
    station_specs = config.cwa_history_station_specs
    fetched_at = datetime.now(TAIPEI)

    async with httpx.AsyncClient(
        timeout=max(config.request_timeout_seconds, 20),
        verify=config.cwa_verify_ssl,
        headers={"User-Agent": "Mozilla/5.0 microclimate-collector/1.0"},
    ) as client:
        tasks = [
            fetch_station_history(client, spec, start=start, end=end, fetched_at=fetched_at)
            for spec in station_specs
        ]
        results = await asyncio.gather(*tasks)

    observations = [obs for station_observations in results for obs in station_observations]
    observations.sort(key=lambda obs: (obs.station_id, obs.obs_time))
    return observations


def latest_codis_history_end(now: datetime | None = None) -> datetime:
    current = now or datetime.now(TAIPEI)
    return current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)


async def fetch_station_history(
    client: httpx.AsyncClient,
    station_spec: dict[str, str],
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> list[TwPortObservation]:
    observations: list[TwPortObservation] = []
    for day_start, day_end in day_ranges(start, end):
        payload = await post_codis_station(client, station_spec, day_start, day_end)
        rows = extract_codis_rows(payload)
        for row in rows:
            observation = normalize_codis_row(row, station_spec, fetched_at=fetched_at)
            if observation and observation.obs_time.minute == 0 and start <= observation.obs_time <= end:
                observations.append(observation)
    return observations


async def post_codis_station(
    client: httpx.AsyncClient,
    station_spec: dict[str, str],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    response = await client.post(
        CODIS_STATION_URL,
        data={
            "type": "report_date",
            "stn_ID": station_spec["station_id"],
            "stn_type": station_spec["station_type"],
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "item": "AirTemperature",
        },
    )
    response.raise_for_status()
    return response.json()


def day_ranges(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    ranges = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while current <= end:
        day_start = max(start, current)
        day_end = min(end, current.replace(hour=23, minute=59, second=59))
        ranges.append((day_start, day_end))
        current = current + timedelta(days=1)
    return ranges


def extract_codis_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for station_payload in data:
        if not isinstance(station_payload, dict):
            continue
        dts = station_payload.get("dts")
        if isinstance(dts, list):
            rows.extend(item for item in dts if isinstance(item, dict))
    return rows


def normalize_codis_row(
    row: dict[str, Any],
    station_spec: dict[str, str],
    fetched_at: datetime,
) -> TwPortObservation | None:
    obs_time = parse_codis_time(row.get("DataTime"))
    if obs_time is None:
        return None

    raw_data = {"codis": row}
    return TwPortObservation(
        source="cwa_history",
        port_code=None,
        station_id=station_spec["station_id"],
        station_name=station_spec["station_name"],
        location=None,
        device_type="WEATHER",
        obs_time=obs_time,
        wind_speed=nested_float(row, "WindSpeed", "Mean"),
        wind_gust=nested_float(row, "PeakGust", "Maximum"),
        wind_direction=nested_float(row, "WindDirection", "Mean"),
        wind_gust_direction=nested_float(row, "PeakGust", "Direction"),
        precipitation_1hr=nested_float(row, "Precipitation", "Accumulation"),
        air_temperature=nested_float(row, "AirTemperature", "Instantaneous"),
        relative_humidity=nested_float(row, "RelativeHumidity", "Instantaneous"),
        air_pressure=nested_float(row, "StationPressure", "Instantaneous"),
        visibility=visibility_meters(row),
        raw_data=raw_data,
        raw_last_data_str=json.dumps(raw_data, ensure_ascii=False),
        stale=False,
        fetched_at=fetched_at,
    )


def parse_codis_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI)


def nested_float(row: dict[str, Any], key: str, nested_key: str) -> float | None:
    value = row.get(key)
    if not isinstance(value, dict):
        return None
    return to_float(value.get(nested_key))


def visibility_meters(row: dict[str, Any]) -> float | None:
    value = nested_float(row, "Visibility", "AutoMean")
    if value is None:
        value = nested_float(row, "Visibility", "Instantaneous")
    if value is None:
        return None
    return value * 1000


def to_float(value: Any) -> float | None:
    if value in ("", None, "-", "-99", "-999", "NaN"):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
