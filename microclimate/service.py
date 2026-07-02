from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from .collector_cwa import CwaCollector
from .collector_twport import TwPortCollector
from .config import Settings
from .forecast_engine import build_forecast
from .models import Observation, UTC, observation_to_api_dict
from .storage import ObservationStore


logger = logging.getLogger(__name__)


class MicroclimateService:
    def __init__(self, settings: Settings, store: ObservationStore) -> None:
        self.settings = settings
        self.store = store
        self.twport = TwPortCollector(settings)
        self.cwa = CwaCollector(settings)

    async def fetch_all(self) -> dict[str, Any]:
        results = await asyncio.gather(
            self._fetch_source("A", self.twport.fetch),
            self._fetch_source("B", self.cwa.fetch),
            return_exceptions=False,
        )
        observations = [obs for result in results for obs in result["observations"]]
        written = self.store.upsert_many(observations)
        self.store.prune_older_than(hours=3)
        forecasts = build_forecast(self.store.recent_history(hours=2), minutes=90)
        forecast_written = self.store.upsert_many(forecasts)
        return {
            "written": written,
            "forecast_written": forecast_written,
            "sources": [{k: v for k, v in result.items() if k != "observations"} for result in results],
        }

    async def _fetch_source(self, source: str, fetcher: Any) -> dict[str, Any]:
        try:
            observations = await fetcher()
            return {"source": source, "ok": True, "count": len(observations), "observations": observations}
        except Exception as exc:
            logger.exception("collector %s failed", source)
            return {"source": source, "ok": False, "count": 0, "error": str(exc), "observations": []}

    def current(self) -> dict[str, Any]:
        latest = self.store.latest_observations(include_forecast=False)
        usable = [obs for obs in latest if not self.is_stale(obs, minutes=20)]
        baseline = self.pick_baseline(usable)
        all_stale = bool(latest) and not usable
        data_unavailable = not baseline or self.all_sources_stale(latest, minutes=30)
        return {
            "data": observation_to_api_dict(baseline, stale=False) if baseline else None,
            "alert": self.has_alert(baseline) if baseline else False,
            "data_quality": {
                "available_sources": sorted({obs.source for obs in latest}),
                "selected_source": baseline.source if baseline else None,
                "stale": all_stale,
                "data_unavailable": data_unavailable,
            },
        }

    def forecast(self, minutes: int = 90) -> dict[str, Any]:
        minutes = max(0, min(minutes, 90))
        history = self.store.recent_history(hours=2)
        forecasts = build_forecast(history, minutes=minutes)
        return {
            "minutes": minutes,
            "data": [
                {
                    **observation_to_api_dict(obs, stale=False),
                    "alert": self.has_alert(obs),
                }
                for obs in forecasts
            ],
            "data_quality": {
                "points": len(forecasts),
                "source_priority": "A then B",
                "data_unavailable": not forecasts,
            },
        }

    @staticmethod
    def pick_baseline(observations: list[Observation]) -> Observation | None:
        if not observations:
            return None
        return sorted(
            observations,
            key=lambda obs: (
                0 if obs.source == "A" else 1 if obs.source == "B" else 2,
                -obs.obs_time.timestamp(),
            ),
        )[0]

    @staticmethod
    def is_stale(observation: Observation, minutes: int) -> bool:
        return observation.obs_time < datetime.now(UTC) - timedelta(minutes=minutes)

    def all_sources_stale(self, observations: list[Observation], minutes: int) -> bool:
        return bool(observations) and all(self.is_stale(obs, minutes) for obs in observations)

    def has_alert(self, observation: Observation | None) -> bool:
        if not observation:
            return False
        return (
            observation.wind_speed is not None
            and observation.wind_speed > self.settings.alert_wind_speed
        ) or (
            observation.wind_gust is not None
            and observation.wind_gust > self.settings.alert_wind_gust
        )
