from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import TAIPEI, TwPortObservation
from app.storage import observation_status


SCHEMA_VERSION = "microclimate.v1"
TIME_ZONE = "Asia/Taipei"
OBSERVATION_CONTRACT = {
    "record_id": "Stable string composed from source/device/station/forecast flag/observed_at.",
    "source": "Data source id, e.g. twport, cwa, cwa_historyapi, cwa_marine_history.",
    "device_type": "Normalized data type, e.g. WIND, WEATHER, MARINE, TIDE, WAVE.",
    "station": {
        "station_id": "Source station identifier.",
        "station_name": "Human-readable station name.",
        "location": "Station location or marine area.",
        "port_code": "Port code when supplied by source.",
        "longitude": "Decimal degrees, WGS84 when available.",
        "latitude": "Decimal degrees, WGS84 when available.",
        "elevation": "Meters when available.",
    },
    "time": {
        "observed_at": "ISO8601 Asia/Taipei observation time.",
        "fetched_at": "ISO8601 Asia/Taipei fetch time, nullable for derived records.",
        "time_zone": TIME_ZONE,
    },
    "metrics": {
        "wind_speed_mps": "m/s",
        "wind_gust_mps": "m/s",
        "wind_direction_deg": "degrees 0-360",
        "wind_gust_direction_deg": "degrees 0-360",
        "precipitation_10min_mm": "mm",
        "precipitation_1hr_mm": "mm",
        "precipitation_24hr_mm": "mm",
        "air_temperature_c": "Celsius",
        "relative_humidity_percent": "%",
        "air_pressure_hpa": "hPa when supplied by source",
        "visibility_m": "meters",
        "tide_level": "Unit indicated by tide_level_unit",
        "tide_level_unit": "m, cm, raw, or source-specific nullable string",
        "wave_height_m": "meters",
        "wave_period_s": "seconds",
        "wave_max_height_m": "meters",
        "current_speed_mps": "m/s",
        "current_direction_deg": "degrees 0-360",
    },
    "quality": {
        "is_forecast": "boolean",
        "confidence": "high, medium, low",
        "stale_at_fetch": "boolean from collector/storage time",
        "status_level": "current, stale, outage, or null when not evaluated",
        "status_label": "Human-readable status label or null",
        "is_stale_now": "boolean or null when not evaluated",
        "obs_age_minutes": "integer minutes or null",
        "fetch_age_minutes": "integer minutes or null",
        "threshold_minutes": "integer minutes or null",
        "expected_update_interval": "Human-readable expected update interval or null",
    },
}


def schema_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/schema",
        metadata={
            "schema_version": SCHEMA_VERSION,
            "compatibility": "Fields documented here are stable for v1. Additive metadata may appear; breaking changes require a new schema_version.",
            "observation_record": OBSERVATION_CONTRACT,
            "stable_endpoints": [
                "/api/v1/microclimate/current",
                "/api/v1/microclimate/forecast",
                "/api/v1/cwa/history",
                "/api/v1/schema",
            ],
        },
        data=[],
        data_quality={"record_count": 0},
    )


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def observation_record(
    observation: TwPortObservation,
    *,
    generated_at: datetime | None = None,
    include_runtime_status: bool = False,
) -> dict[str, Any]:
    generated = generated_at or now_taipei()
    status = observation_status(observation, generated, None) if include_runtime_status else None
    observed_at = observation.obs_time.astimezone(TAIPEI).isoformat()
    fetched_at = observation.fetched_at.astimezone(TAIPEI).isoformat() if observation.fetched_at else None

    return {
        "record_id": stable_record_id(observation),
        "source": observation.source,
        "device_type": observation.device_type,
        "station": {
            "station_id": observation.station_id,
            "station_name": observation.station_name,
            "location": observation.location,
            "port_code": observation.port_code,
            "longitude": observation.longitude,
            "latitude": observation.latitude,
            "elevation": observation.elevation,
        },
        "time": {
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "time_zone": TIME_ZONE,
        },
        "metrics": {
            "wind_speed_mps": observation.wind_speed,
            "wind_gust_mps": observation.wind_gust,
            "wind_direction_deg": observation.wind_direction,
            "wind_gust_direction_deg": observation.wind_gust_direction,
            "precipitation_10min_mm": observation.precipitation_10min,
            "precipitation_1hr_mm": observation.precipitation_1hr,
            "precipitation_24hr_mm": observation.precipitation_24hr,
            "air_temperature_c": observation.air_temperature,
            "relative_humidity_percent": observation.relative_humidity,
            "air_pressure_hpa": observation.air_pressure,
            "visibility_m": observation.visibility,
            "tide_level": observation.tide_level,
            "tide_level_unit": observation.tide_level_unit,
            "wave_height_m": observation.wave_height,
            "wave_period_s": observation.wave_period,
            "wave_max_height_m": observation.wave_max_height,
            "current_speed_mps": observation.current_speed,
            "current_direction_deg": observation.current_direction,
        },
        "quality": {
            "is_forecast": observation.is_forecast,
            "confidence": observation.confidence,
            "stale_at_fetch": observation.stale,
            "status_level": status["status_level"] if status else None,
            "status_label": status["status_label"] if status else None,
            "is_stale_now": status["is_stale_now"] if status else None,
            "obs_age_minutes": status["obs_age_minutes"] if status else None,
            "fetch_age_minutes": status["fetch_age_minutes"] if status else None,
            "threshold_minutes": status["threshold_minutes"] if status else None,
            "expected_update_interval": status["expected_update_interval"] if status else None,
        },
    }


def stable_record_id(observation: TwPortObservation) -> str:
    observed_at = observation.obs_time.astimezone(TAIPEI).isoformat()
    forecast_flag = "forecast" if observation.is_forecast else "observed"
    return ":".join(
        [
            observation.source,
            observation.device_type,
            observation.station_id,
            forecast_flag,
            observed_at,
        ]
    )


def response_envelope(
    *,
    endpoint: str,
    generated_at: datetime | None = None,
    request: dict[str, Any] | None = None,
    data: list[dict[str, Any]] | None = None,
    data_quality: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = generated_at or now_taipei()
    return {
        "schema_version": SCHEMA_VERSION,
        "endpoint": endpoint,
        "generated_at": generated.astimezone(TAIPEI).isoformat(),
        "time_zone": TIME_ZONE,
        "request": request or {},
        "metadata": metadata or {},
        "data_quality": data_quality or {},
        "data": data or [],
    }


def current_response(observations: list[TwPortObservation]) -> dict[str, Any]:
    generated = now_taipei()
    records = [
        observation_record(observation, generated_at=generated, include_runtime_status=True)
        for observation in observations
    ]
    stale_records = [record for record in records if record["quality"]["is_stale_now"]]
    return response_envelope(
        endpoint="/api/v1/microclimate/current",
        generated_at=generated,
        data=records,
        data_quality={
            "record_count": len(records),
            "stale_count": len(stale_records),
            "contains_stale": bool(stale_records),
            "status_method": "Runtime freshness is evaluated by source/device policy at response time.",
        },
        metadata={
            "contract": "Stable flat observation list. New fields may be added only under metadata or a future schema_version.",
        },
    )


def forecast_response(minutes: int, observations: list[TwPortObservation]) -> dict[str, Any]:
    generated = now_taipei()
    return response_envelope(
        endpoint="/api/v1/microclimate/forecast",
        generated_at=generated,
        request={"minutes": minutes},
        data=[
            observation_record(observation, generated_at=generated, include_runtime_status=False)
            for observation in observations
        ],
        data_quality={
            "record_count": len(observations),
            "method": "linear wind_speed projection; persistence when history is insufficient",
            "forecast_horizon_minutes": minutes,
        },
    )


def history_response(
    *,
    source: str,
    hours: int,
    observations: list[TwPortObservation],
    query_start: str | None,
    query_end: str | None,
    note: str,
    source_config: dict[str, Any],
) -> dict[str, Any]:
    generated = now_taipei()
    return response_envelope(
        endpoint="/api/v1/cwa/history",
        generated_at=generated,
        request={"source": source, "hours": hours},
        data=[
            observation_record(observation, generated_at=generated, include_runtime_status=False)
            for observation in observations
        ],
        data_quality={
            "record_count": len(observations),
            "query_start": query_start,
            "query_end": query_end,
            "saved_to_local_db": False,
            "note": note,
        },
        metadata={
            "source_config": source_config,
        },
    )
