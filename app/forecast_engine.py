from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta

from app.models import TAIPEI, TwPortObservation


def build_wind_forecast(history: list[TwPortObservation], minutes: int = 90) -> list[TwPortObservation]:
    targets = [offset for offset in [10, 30, 60, 90] if offset <= minutes]
    wind_history = [obs for obs in history if obs.wind_speed is not None]
    grouped: dict[tuple[str, str], list[TwPortObservation]] = defaultdict(list)
    for obs in sorted(wind_history, key=lambda item: item.obs_time):
        grouped[(obs.station_id, obs.device_type)].append(obs)

    forecasts: list[TwPortObservation] = []
    now = datetime.now(TAIPEI)
    for observations in grouped.values():
        latest = observations[-1]
        for offset in targets:
            forecast = replace(
                latest,
                obs_time=now + timedelta(minutes=offset),
                wind_speed=project_wind_speed(observations, offset),
                is_forecast=True,
                confidence="medium" if len(observations) >= 2 else "low",
                stale=False,
                fetched_at=now,
            )
            forecasts.append(forecast)
    return forecasts


def project_wind_speed(observations: list[TwPortObservation], offset_minutes: int) -> float | None:
    points = [obs for obs in observations if obs.wind_speed is not None]
    if not points:
        return None
    if len(points) < 2:
        return points[-1].wind_speed
    first = points[0]
    latest = points[-1]
    elapsed = max((latest.obs_time - first.obs_time).total_seconds() / 60, 1)
    slope = (float(latest.wind_speed) - float(first.wind_speed)) / elapsed
    return round(float(latest.wind_speed) + slope * offset_minutes, 3)
