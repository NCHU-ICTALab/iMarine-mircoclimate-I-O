from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.collectors.cwa import parse_cwa_time, text, to_float
from app.config import Settings, settings
from app.models import TAIPEI, TwPortObservation


logger = logging.getLogger(__name__)

MARINE_DATASTORE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/{data_id}"
ALLOWED_HISTORY_HOURS = (6, 12, 24, 48)
MARINE_STATION_METADATA_SOURCE = "https://www.cwa.gov.tw/Data/js/marine/MMC_stations.js"
MARINE_SOURCE_NOTES = {
    "coverage": "O-B0075-001 provides rolling 48-hour sea surface observations.",
    "update_interval": "About every 4 hours by specification; rows are usually hourly.",
    "selection_note": "Default stations focus on Kaohsiung Harbor tide, nearby Kaohsiung coast tide, and southern offshore buoy references.",
}
MARINE_STATION_METADATA: dict[str, dict[str, str]] = {
    "C4P01": {
        "station_name": "高雄潮位站",
        "station_name_en": "Kaohsiung",
        "area_name": "高雄枋寮沿海",
        "station_longitude": "120.2883",
        "station_latitude": "22.6144",
        "station_address": "高雄港",
        "selection_role": "primary_tide",
    },
    "1786": {
        "station_name": "永安潮位站",
        "station_name_en": "Yong'an",
        "area_name": "安平高雄沿海",
        "station_longitude": "120.1975",
        "station_latitude": "22.8189",
        "station_address": "高雄市新港海堤外側，永安中油 LNG 港防波堤頭",
        "selection_role": "nearby_tide_north",
    },
    "COMC08": {
        "station_name": "彌陀資料浮標",
        "station_name_en": "Mituo Buoy",
        "area_name": "安平高雄沿海",
        "station_longitude": "120.1636",
        "station_latitude": "22.7636",
        "station_address": "高雄市彌陀區外海，水深約 23 公尺",
        "selection_role": "nearby_buoy_north",
    },
    "46714D": {
        "station_name": "小琉球資料浮標",
        "station_name_en": "Xiao Liuqiu Buoy",
        "area_name": "枋寮恆春沿海",
        "station_longitude": "120.3781",
        "station_latitude": "22.3172",
        "station_address": "小琉球大福漁港外海南南東方約 2 公里，水深約 100 公尺",
        "selection_role": "nearby_buoy_south",
    },
    "C4Q02": {
        "station_name": "東港潮位站",
        "station_name_en": "Donggang",
        "area_name": "高雄枋寮沿海",
        "station_longitude": "120.4383",
        "station_latitude": "22.4651",
        "station_address": "東港漁港",
        "selection_role": "nearby_tide_south",
    },
    "C4Q01": {
        "station_name": "小琉球潮位站",
        "station_name_en": "Xiao Liuqiu",
        "area_name": "高雄枋寮沿海",
        "station_longitude": "120.3833",
        "station_latitude": "22.3533",
        "station_address": "屏東縣琉球鄉中福村白沙尾漁港紅燈塔邊",
        "selection_role": "nearby_tide_south",
    },
}


async def collect_marine_history(hours: int = 48, config: Settings = settings) -> list[TwPortObservation]:
    if hours not in ALLOWED_HISTORY_HOURS:
        raise ValueError(f"hours must be one of {ALLOWED_HISTORY_HOURS}")
    if not config.cwa_api_key:
        logger.warning("CWA_API_KEY is not configured; skip CWA marine history collector")
        return []

    fetched_at = datetime.now(TAIPEI)
    end = fetched_at
    start = end - timedelta(hours=hours)
    async with httpx.AsyncClient(timeout=max(config.request_timeout_seconds, 30), verify=config.cwa_verify_ssl) as client:
        response = await client.get(
            MARINE_DATASTORE_URL.format(data_id=config.cwa_marine_data_id),
            params={"Authorization": config.cwa_api_key, "format": "JSON"},
        )
        response.raise_for_status()
        payload = response.json()

    observations = parse_marine_payload(payload, start=start, end=end, fetched_at=fetched_at, config=config)
    observations.sort(key=lambda obs: (obs.station_id, obs.obs_time))
    return observations


async def inspect_marine_history(config: Settings = settings) -> dict[str, Any]:
    if not config.cwa_api_key:
        return {"configured": False, "error": "CWA_API_KEY is not configured"}

    async with httpx.AsyncClient(timeout=max(config.request_timeout_seconds, 30), verify=config.cwa_verify_ssl) as client:
        response = await client.get(
            MARINE_DATASTORE_URL.format(data_id=config.cwa_marine_data_id),
            params={"Authorization": config.cwa_api_key, "format": "JSON"},
        )
        response.raise_for_status()
        payload = response.json()

    locations = (
        payload.get("Records", {})
        .get("SeaSurfaceObs", {})
        .get("Location", [])
    )
    station_filter = set(config.cwa_marine_station_id_list)
    station_summaries = []
    for location in locations if isinstance(locations, list) else []:
        station = location.get("Station") if isinstance(location, dict) and isinstance(location.get("Station"), dict) else {}
        station_id = text(station.get("StationID")) or text(station.get("StationId"))
        if station_filter and station_id not in station_filter:
            continue
        times = location.get("StationObsTimes", {}).get("StationObsTime", []) if isinstance(location, dict) else []
        latest = max((item.get("DateTime", "") for item in times if isinstance(item, dict)), default=None)
        metadata = marine_station_metadata(station_id or "")
        station_summaries.append(
            {
                "station_id": station_id,
                "station_name": metadata.get("station_name") or station_id,
                "area_name": metadata.get("area_name"),
                "selection_role": metadata.get("selection_role"),
                "rows": len(times) if isinstance(times, list) else 0,
                "latest_obs_time": latest,
                "longitude": to_float(metadata.get("station_longitude")),
                "latitude": to_float(metadata.get("station_latitude")),
                "address": metadata.get("station_address"),
            }
        )

    return {
        "configured": True,
        "data_id": config.cwa_marine_data_id,
        "metadata_source": MARINE_STATION_METADATA_SOURCE,
        "source_notes": MARINE_SOURCE_NOTES,
        "selected_station_ids": config.cwa_marine_station_id_list,
        "stations": station_summaries,
    }


def parse_marine_payload(
    payload: dict[str, Any],
    start: datetime,
    end: datetime,
    fetched_at: datetime,
    config: Settings = settings,
) -> list[TwPortObservation]:
    locations = (
        payload.get("Records", {})
        .get("SeaSurfaceObs", {})
        .get("Location", [])
    )
    if not isinstance(locations, list):
        return []

    station_filter = set(config.cwa_marine_station_id_list)
    observations: list[TwPortObservation] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        station = location.get("Station") if isinstance(location.get("Station"), dict) else {}
        station_id = text(station.get("StationID")) or text(station.get("StationId"))
        if station_filter and station_id not in station_filter:
            continue
        metadata = marine_station_metadata(station_id or "")
        station_name = text(station.get("StationName")) or metadata.get("station_name") or station_id or "unknown"
        station_times = location.get("StationObsTimes", {}).get("StationObsTime", [])
        if not isinstance(station_times, list):
            continue
        for row in station_times:
            if not isinstance(row, dict):
                continue
            observation = normalize_marine_row(
                row,
                station_id=station_id or "unknown",
                station_name=station_name,
                station=station,
                metadata=metadata,
                fetched_at=fetched_at,
            )
            if observation and start <= observation.obs_time <= end:
                observations.append(observation)
    return observations


def normalize_marine_row(
    row: dict[str, Any],
    station_id: str,
    station_name: str,
    station: dict[str, Any],
    metadata: dict[str, str] | None,
    fetched_at: datetime,
) -> TwPortObservation | None:
    obs_time = parse_cwa_time(row.get("DateTime"))
    if obs_time is None:
        return None
    elements = row.get("WeatherElements") if isinstance(row.get("WeatherElements"), dict) else {}
    anemometer = elements.get("PrimaryAnemometer") if isinstance(elements.get("PrimaryAnemometer"), dict) else {}
    current_layer = first_current_layer(elements)
    station_metadata = metadata or {}
    raw_data = {
        "marine_station": station,
        "marine_station_metadata": station_metadata,
        "marine_observation": row,
    }

    return TwPortObservation(
        source="cwa_marine_history",
        port_code=None,
        station_id=station_id,
        station_name=station_name,
        location=station_metadata.get("area_name") or station_metadata.get("station_address"),
        device_type="MARINE",
        obs_time=obs_time,
        longitude=to_float(
            station.get("StationLongitude")
            or station.get("Longitude")
            or station_metadata.get("station_longitude")
        ),
        latitude=to_float(
            station.get("StationLatitude")
            or station.get("Latitude")
            or station_metadata.get("station_latitude")
        ),
        wind_speed=to_float(anemometer.get("WindSpeed")),
        wind_gust=to_float(anemometer.get("MaximumWindSpeed")),
        wind_direction=to_float(anemometer.get("WindDirection")),
        air_temperature=to_float(elements.get("Temperature")),
        air_pressure=to_float(elements.get("StationPressure")),
        tide_level=to_float(elements.get("TideHeight")),
        tide_level_unit="m",
        wave_height=to_float(elements.get("WaveHeight")),
        wave_period=to_float(elements.get("WavePeriod")),
        current_speed=to_float(current_layer.get("CurrentSpeed")) if current_layer else None,
        current_direction=to_float(current_layer.get("CurrentDirection")) if current_layer else None,
        raw_data=raw_data,
        raw_last_data_str=json.dumps(raw_data, ensure_ascii=False),
        stale=False,
        fetched_at=fetched_at,
    )


def first_current_layer(elements: dict[str, Any]) -> dict[str, Any] | None:
    currents = elements.get("SeaCurrents")
    if not isinstance(currents, dict):
        return None
    layer = currents.get("Layer")
    if isinstance(layer, list):
        return next((item for item in layer if isinstance(item, dict)), None)
    if isinstance(layer, dict):
        return layer
    return None


def marine_station_metadata(station_id: str) -> dict[str, str]:
    return MARINE_STATION_METADATA.get(station_id, {})
