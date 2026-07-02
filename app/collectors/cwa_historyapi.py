from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree

import httpx

from app.collectors.cwa import parse_cwa_time, text, to_float
from app.config import Settings, settings
from app.models import TAIPEI, TwPortObservation


logger = logging.getLogger(__name__)

ALLOWED_HISTORY_HOURS = (6, 12, 24, 48)
HISTORY_METADATA_URL = "https://opendata.cwa.gov.tw/historyapi/v1/getMetadata/{data_id}"
HISTORY_DATA_ID_LIST_URL = "https://opendata.cwa.gov.tw/historyapi/v1/getDataId/list"
HISTORY_SOURCE_NOTES = {
    "coverage": "CWA historyapi supports timeFrom/timeTo and returns ProductURL files for the selected dataid.",
    "update_interval": "O-A0001-001 is usually hourly; downloaded product files may be XML even when metadata is JSON.",
    "selection_note": "Default dataid is O-A0001-001 because it contains automatic weather station observations for Kaohsiung area stations.",
}


async def collect_historyapi(hours: int = 24, config: Settings = settings) -> list[TwPortObservation]:
    if hours not in ALLOWED_HISTORY_HOURS:
        raise ValueError(f"hours must be one of {ALLOWED_HISTORY_HOURS}")
    if not config.cwa_api_key:
        logger.warning("CWA_API_KEY is not configured; skip CWA historyapi collector")
        return []

    end = datetime.now(TAIPEI).replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    fetched_at = datetime.now(TAIPEI)

    async with httpx.AsyncClient(
        timeout=max(config.request_timeout_seconds, 30),
        verify=config.cwa_verify_ssl,
        follow_redirects=True,
    ) as client:
        metadata = await fetch_metadata(client, config, start=start, end=end)
        product_urls = extract_product_urls(metadata)
        observations: list[TwPortObservation] = []
        for product_url in product_urls:
            observations.extend(await fetch_product(client, product_url, fetched_at=fetched_at, config=config))

    observations = dedupe_observations(observations)
    observations.sort(key=lambda obs: (obs.station_id, obs.obs_time))
    return observations


async def fetch_metadata(
    client: httpx.AsyncClient,
    config: Settings,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    response = await client.get(
        HISTORY_METADATA_URL.format(data_id=config.cwa_history_data_id),
        params={
            "Authorization": config.cwa_api_key,
            "format": "JSON",
            "timeFrom": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeTo": end.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    response.raise_for_status()
    return response.json()


async def inspect_historyapi(hours: int = 6, config: Settings = settings) -> dict[str, Any]:
    if hours not in ALLOWED_HISTORY_HOURS:
        raise ValueError(f"hours must be one of {ALLOWED_HISTORY_HOURS}")
    if not config.cwa_api_key:
        return {"configured": False, "error": "CWA_API_KEY is not configured"}

    end = datetime.now(TAIPEI).replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    async with httpx.AsyncClient(
        timeout=max(config.request_timeout_seconds, 30),
        verify=config.cwa_verify_ssl,
        follow_redirects=True,
    ) as client:
        data_id_response = await client.get(
            HISTORY_DATA_ID_LIST_URL,
            params={"Authorization": config.cwa_api_key, "format": "JSON"},
        )
        data_id_response.raise_for_status()
        data_id_payload = data_id_response.json()
        metadata = await fetch_metadata(client, config, start=start, end=end)

    product_urls = extract_product_urls(metadata)
    return {
        "configured": True,
        "data_id": config.cwa_history_data_id,
        "source_notes": HISTORY_SOURCE_NOTES,
        "data_id_list_returned_keys": list(data_id_payload.keys()) if isinstance(data_id_payload, dict) else None,
        "data_id_list_is_empty": data_id_payload == {},
        "query_start": start.isoformat(),
        "query_end": end.isoformat(),
        "metadata_product_url_count": len(product_urls),
        "sample_product_urls": [redact_authorization(url) for url in product_urls[:5]],
        "station_filters": {
            "station_names": config.cwa_station_name_list,
            "county_names": config.cwa_county_name_list,
        },
    }


def extract_product_urls(payload: Any) -> list[str]:
    urls: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            product_url = value.get("ProductURL")
            if isinstance(product_url, str) and product_url:
                urls.append(product_url)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return urls


def redact_authorization(url: str) -> str:
    if "Authorization=" not in url:
        return url
    prefix, _, rest = url.partition("Authorization=")
    suffix = ""
    if "&" in rest:
        _, _, suffix = rest.partition("&")
        suffix = "&" + suffix
    return prefix + "Authorization=***" + suffix


async def fetch_product(
    client: httpx.AsyncClient,
    product_url: str,
    fetched_at: datetime,
    config: Settings,
) -> list[TwPortObservation]:
    response = await client.get(product_url)
    response.raise_for_status()
    xml_text = response.content.decode("utf-8", errors="replace")
    return parse_history_xml(xml_text, fetched_at=fetched_at, config=config)


def parse_history_xml(xml_text: str, fetched_at: datetime, config: Settings = settings) -> list[TwPortObservation]:
    root = ElementTree.fromstring(xml_text)
    observations: list[TwPortObservation] = []
    for station in root.findall(".//{*}Station"):
        observation = normalize_station_element(station, fetched_at=fetched_at, config=config)
        if observation is not None:
            observations.append(observation)
    return observations


def normalize_station_element(
    station: ElementTree.Element,
    fetched_at: datetime,
    config: Settings = settings,
) -> TwPortObservation | None:
    station_name = child_text(station, "StationName")
    station_id = child_text(station, "StationId")
    if not station_name and not station_id:
        return None

    targets = config.cwa_station_name_list
    if targets and station_name and not any(target in station_name for target in targets):
        return None

    county_name = child_text(station, "CountyName")
    town_name = child_text(station, "TownName")
    counties = config.cwa_county_name_list
    if counties and county_name and not any(county in county_name for county in counties):
        return None

    obs_time = parse_cwa_time(child_text(station, "DateTime")) or fetched_at
    wind_direction = child_float(station, "WindDirection")
    gust_element = first_child(station, "GustInfo")
    gust_speed = child_float(gust_element, "PeakGustSpeed") if gust_element is not None else None
    gust_direction = child_float(gust_element, "WindDirection") if gust_element is not None else None
    now_element = first_child(station, "Now")
    coordinates = [element_to_dict(item) for item in station.findall(".//{*}Coordinates")]

    raw_data = {"historyapi_station": element_to_dict(station)}
    return TwPortObservation(
        source="cwa_historyapi",
        port_code=None,
        station_id=station_id or station_name or "unknown",
        station_name=station_name or station_id or "unknown",
        location=town_name or county_name,
        device_type="WEATHER",
        obs_time=obs_time,
        longitude=coordinate_value(coordinates, "StationLongitude"),
        latitude=coordinate_value(coordinates, "StationLatitude"),
        elevation=child_float(station, "StationAltitude"),
        wind_speed=child_float(station, "WindSpeed"),
        wind_gust=gust_speed,
        wind_direction=wind_direction,
        wind_gust_direction=gust_direction,
        precipitation_1hr=child_float(now_element, "Precipitation") if now_element is not None else None,
        air_temperature=child_float(station, "AirTemperature"),
        relative_humidity=child_float(station, "RelativeHumidity"),
        air_pressure=child_float(station, "AirPressure"),
        visibility=child_float(station, "Visibility"),
        raw_data=raw_data,
        stale=False,
        fetched_at=fetched_at,
    )


def child_text(element: ElementTree.Element | None, name: str) -> str | None:
    if element is None:
        return None
    child = first_child(element, name)
    return text(child.text) if child is not None else None


def child_float(element: ElementTree.Element | None, name: str) -> float | None:
    return to_float(child_text(element, name))


def first_child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return element.find(f".//{{*}}{name}")


def element_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    children = list(element)
    if not children:
        return {strip_namespace(element.tag): text(element.text)}
    data: dict[str, Any] = {}
    for child in children:
        key = strip_namespace(child.tag)
        value = element_to_dict(child)
        value = value.get(key) if list(child) == [] else value
        if key in data:
            if not isinstance(data[key], list):
                data[key] = [data[key]]
            data[key].append(value)
        else:
            data[key] = value
    return data


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def coordinate_value(coordinates: list[dict[str, Any]], key: str) -> float | None:
    for coordinate in coordinates:
        if coordinate.get("CoordinateName") == "WGS84":
            value = to_float(coordinate.get(key))
            if value is not None:
                return value
    for coordinate in coordinates:
        value = to_float(coordinate.get(key))
        if value is not None:
            return value
    return None


def dedupe_observations(observations: list[TwPortObservation]) -> list[TwPortObservation]:
    deduped: dict[tuple[str, datetime], TwPortObservation] = {}
    for observation in observations:
        deduped[(observation.station_id, observation.obs_time)] = observation
    return list(deduped.values())
