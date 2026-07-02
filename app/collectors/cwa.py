from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings, settings
from app.models import TAIPEI, TwPortObservation
from app.storage import ObservationStore


logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def build_cwa_url(config: Settings = settings) -> str:
    return f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{config.cwa_data_id}"


async def collect(config: Settings = settings) -> list[TwPortObservation]:
    if not config.cwa_api_key:
        logger.warning("CWA_API_KEY is not configured; skip CWA collector")
        return []

    params = {"Authorization": config.cwa_api_key, "format": "JSON"}
    async with httpx.AsyncClient(timeout=config.request_timeout_seconds, verify=config.cwa_verify_ssl) as client:
        response = await client.get(build_cwa_url(config), params=params)
        response.raise_for_status()
        payload = response.json()

    fetched_at = datetime.now(TAIPEI)
    stations = find_station_records(payload)
    observations = []
    for record in stations:
        observation = normalize_cwa_record(record, fetched_at=fetched_at, config=config)
        if observation is not None:
            observations.append(observation)
    return observations


def find_station_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records", {})
    candidates = [
        records.get("Station"),
        records.get("station"),
        records.get("location"),
        records.get("Location"),
        payload.get("Station"),
        payload.get("data"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def normalize_cwa_record(
    record: dict[str, Any],
    fetched_at: datetime,
    config: Settings = settings,
) -> TwPortObservation | None:
    station_name = text(first_present(record, ["StationName", "stationName", "locationName", "LocationName"]))
    station_id = text(first_present(record, ["StationId", "StationID", "stationId", "locationId", "LocationId"]))
    if not station_name and not station_id:
        return None

    targets = config.cwa_station_name_list
    if targets and station_name and not any(target in station_name for target in targets):
        return None

    obs_time = parse_cwa_time(
        nested_get(record, ["ObsTime", "DateTime"])
        or nested_get(record, ["obsTime", "DateTime"])
        or first_present(record, ["obsTime", "time", "DateTime"])
    ) or fetched_at

    weather = record.get("WeatherElement") or record.get("weatherElement") or {}
    gust = record.get("GustInfo") or record.get("gustInfo") or {}
    geo = record.get("GeoInfo") or record.get("geoInfo") or {}
    county_name = text(nested_get(geo, ["CountyName"]) or first_present(record, ["CountyName", "countyName"]))
    town_name = text(nested_get(geo, ["TownName"]) or first_present(record, ["TownName", "townName"]))
    counties = config.cwa_county_name_list
    if counties and county_name and not any(county in county_name for county in counties):
        return None
    coordinates = geo.get("Coordinates") if isinstance(geo, dict) else None
    coordinate = coordinates[0] if isinstance(coordinates, list) and coordinates else {}

    raw_data = {
        "WeatherElement": weather,
        "GustInfo": gust,
        "raw_station": record,
    }

    observation = TwPortObservation(
        source="cwa",
        port_code=None,
        station_id=station_id or station_name or "unknown",
        station_name=station_name or station_id or "unknown",
        location=town_name or county_name,
        device_type="WEATHER",
        obs_time=obs_time,
        longitude=to_float(
            first_present(record, ["StationLongitude", "longitude"])
            or nested_get(geo, ["StationLongitude"])
            or nested_get(coordinate, ["StationLongitude"])
        ),
        latitude=to_float(
            first_present(record, ["StationLatitude", "latitude"])
            or nested_get(geo, ["StationLatitude"])
            or nested_get(coordinate, ["StationLatitude"])
        ),
        wind_speed=cwa_float(record, weather, ["WindSpeed", "風速"]),
        wind_direction=cwa_float(record, weather, ["WindDirection", "風向"]),
        wind_gust=(
            to_float(first_present(gust, ["PeakGustSpeed", "peakGustSpeed"]))
            or cwa_float(record, weather, ["PeakGustSpeed", "GustSpeed", "最大陣風"])
        ),
        precipitation_10min=cwa_float(record, weather, ["Precipitation10Min", "Past10Min", "10分鐘雨量"]),
        precipitation_1hr=cwa_float(record, weather, ["Precipitation1hr", "Past1hr", "Precipitation", "1小時雨量", "降水量"]),
        precipitation_24hr=cwa_float(record, weather, ["Precipitation24hr", "Past24hr", "24小時雨量"]),
        air_temperature=cwa_float(record, weather, ["AirTemperature", "Temperature", "氣溫"]),
        relative_humidity=cwa_float(record, weather, ["RelativeHumidity", "Humidity", "相對濕度"]),
        air_pressure=cwa_float(record, weather, ["AirPressure", "Pressure", "測站氣壓"]),
        visibility=cwa_float(record, weather, ["Visibility", "能見度"]),
        raw_data=raw_data,
        raw_last_data_str=json.dumps(raw_data, ensure_ascii=False),
        stale=(fetched_at - obs_time).total_seconds() > 20 * 60,
        fetched_at=fetched_at,
    )
    return observation


def cwa_float(record: dict[str, Any], weather: Any, names: list[str]) -> float | None:
    direct = to_float(first_present(record, names))
    if direct is not None:
        return direct
    value = find_weather_value(weather, names)
    return to_float(value)


def find_weather_value(weather: Any, names: list[str]) -> Any:
    if isinstance(weather, dict):
        for name in names:
            if name in weather:
                return extract_value(weather[name])
        for value in weather.values():
            found = find_weather_value(value, names)
            if found is not None:
                return found
    if isinstance(weather, list):
        for item in weather:
            if not isinstance(item, dict):
                continue
            element_name = item.get("ElementName") or item.get("elementName")
            if element_name in names:
                return extract_value(item)
            found = find_weather_value(item, names)
            if found is not None:
                return found
    return None


def extract_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ["ElementValue", "elementValue", "Value", "value", "Precipitation", "AirTemperature"]:
        if key in value:
            return extract_value(value[key])
    return None


def first_present(data: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in data and data[name] not in ("", None, "-"):
            return data[name]
    return None


def nested_get(data: Any, path: list[str]) -> Any:
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def parse_cwa_time(value: Any) -> datetime | None:
    if not value:
        return None
    text_value = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                parsed = datetime.strptime(text_value, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            logger.warning("Unable to parse CWA datetime: %s", value)
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI)


def to_float(value: Any) -> float | None:
    if value in ("", None, "-", "-99", "-999", "NaN"):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def text(value: Any) -> str | None:
    if value in ("", None, "-"):
        return None
    return str(value).strip()


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", dest="print_output")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    observations = await collect()
    if args.save:
        store = ObservationStore(settings.database_path)
        store.upsert_many(observations)
    if args.print_output or not args.save:
        print(json.dumps([item.to_dict() for item in observations], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
