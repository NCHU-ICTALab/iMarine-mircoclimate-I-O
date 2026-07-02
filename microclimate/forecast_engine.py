from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta

from .models import Observation, UTC


FORECAST_FIELDS = [
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "precipitation_10min",
    "precipitation_1hr",
    "visibility",
    "tide_level",
    "wave_height",
]


def build_forecast(history: list[Observation], minutes: int = 90) -> list[Observation]:
    if not history:
        return []
    minutes = max(0, min(minutes, 90))
    selected = select_baseline_series(history)
    forecasts: list[Observation] = []
    for station_key, observations in selected.items():
        if not observations:
            continue
        latest = observations[-1]
        for offset in range(0, minutes + 1, 10):
            forecasts.append(project_observation(latest, observations, offset, station_key[0]))
    return forecasts


def select_baseline_series(history: list[Observation]) -> dict[tuple[str, str], list[Observation]]:
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in sorted(history, key=lambda item: item.obs_time):
        grouped[(obs.source, obs.station_id)].append(obs)
    source_a = {key: value for key, value in grouped.items() if key[0] == "A"}
    if source_a:
        return source_a
    return grouped


def project_observation(
    latest: Observation,
    observations: list[Observation],
    offset_minutes: int,
    source: str,
) -> Observation:
    projected = replace(
        latest,
        obs_time=datetime.now(UTC) + timedelta(minutes=offset_minutes),
        is_forecast=offset_minutes > 0,
        confidence=confidence_for(observations, offset_minutes, source),
        fetched_at=datetime.now(UTC),
    )
    for field in FORECAST_FIELDS:
        value = project_field(observations, field, offset_minutes)
        setattr(projected, field, value)
    if projected.precipitation_10min is not None:
        projected.precipitation_10min = max(projected.precipitation_10min, 0)
    if projected.precipitation_1hr is not None:
        projected.precipitation_1hr = max(projected.precipitation_1hr, 0)
    return projected


def project_field(observations: list[Observation], field: str, offset_minutes: int) -> float | None:
    points = [(obs.obs_time, getattr(obs, field)) for obs in observations if getattr(obs, field) is not None]
    if not points:
        return None
    if len(points) < 2 or offset_minutes == 0:
        return float(points[-1][1])
    first_time, first_value = points[0]
    last_time, last_value = points[-1]
    elapsed_minutes = max((last_time - first_time).total_seconds() / 60, 1)
    slope = (float(last_value) - float(first_value)) / elapsed_minutes
    return round(float(last_value) + slope * offset_minutes, 3)


def confidence_for(observations: list[Observation], offset_minutes: int, source: str) -> str:
    if offset_minutes == 0:
        return "high"
    if source != "A" or len(observations) < 2:
        return "low"
    oldest = observations[0].obs_time
    newest = observations[-1].obs_time
    history_minutes = (newest - oldest).total_seconds() / 60
    if history_minutes >= 60 and offset_minutes <= 30:
        return "medium"
    return "low"
