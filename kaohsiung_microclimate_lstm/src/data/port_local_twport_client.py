from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

try:
    from .twport_realtime_parser import parse_twport_realtime_wind_records
except ImportError:  # pragma: no cover
    from twport_realtime_parser import parse_twport_realtime_wind_records

try:
    from app.collectors.twport import HEADERS, parse_gridview1, normalize_row
except ImportError:  # pragma: no cover
    HEADERS = {"User-Agent": "Mozilla/5.0 microclimate-collector/1.0"}
    parse_gridview1 = None
    normalize_row = None


TAIPEI = timezone(timedelta(hours=8))


class PortLocalTwportClient:
    """Client for fetching Kaohsiung Port local station observations from TWPort."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 10,
        retry_attempts: int = 3,
        cache_minutes: int = 10,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = int(timeout_seconds)
        self.retry_attempts = int(retry_attempts)
        self.cache_minutes = int(cache_minutes)
        self.verify_ssl = bool(verify_ssl)
        self._cached_rows: list[dict[str, Any]] | None = None
        self._cached_realtime_records: list[dict[str, Any]] | None = None
        self._cache_time: datetime | None = None
        self._last_error: str | None = None

    def fetch_station_latest(self, station_id: str) -> dict[str, Any]:
        fetched_at = datetime.now(TAIPEI)
        try:
            rows = self._fetch_rows()
            records = [record for record in self._normalize_rows(rows, fetched_at) if _matches_station(record, str(station_id))]
            records.extend([record for record in self._cached_realtime_records or [] if _matches_station(record, str(station_id))])
            return {
                "station_id": str(station_id),
                "available": bool(records),
                "fetched_at": fetched_at.isoformat(timespec="seconds"),
                "raw_records": records,
                "source_url": self.base_url,
                "error": None if records else "No records returned for station.",
            }
        except Exception as exc:
            return {
                "station_id": str(station_id),
                "available": False,
                "fetched_at": fetched_at.isoformat(timespec="seconds"),
                "raw_records": [],
                "source_url": self.base_url,
                "error": str(exc),
            }

    def fetch_station_history(self, station_id: str, start_time: Any = None, end_time: Any = None) -> dict[str, Any]:
        result = self.fetch_station_latest(station_id)
        result["history_requested"] = True
        result["history_range"] = {"start_time": str(start_time) if start_time else None, "end_time": str(end_time) if end_time else None}
        return result

    def fetch_station_pool(self, station_ids: list[str]) -> dict[str, Any]:
        station_results = {str(station_id): self.fetch_station_latest(str(station_id)) for station_id in station_ids}
        available = [station_id for station_id, result in station_results.items() if result.get("available")]
        missing = [station_id for station_id in station_results if station_id not in available]
        return {
            "available_station_ids": available,
            "missing_station_ids": missing,
            "station_results": station_results,
            "fetch_report": {
                "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
                "source": "twport",
                "source_url": self.base_url,
                "requested_count": len(station_ids),
                "available_count": len(available),
                "missing_count": len(missing),
            },
        }

    def _fetch_rows(self) -> list[dict[str, Any]]:
        now = datetime.now(TAIPEI)
        if self._cached_rows is not None and self._cache_time is not None:
            if (now - self._cache_time).total_seconds() <= self.cache_minutes * 60:
                return self._cached_rows
        last_error: Exception | None = None
        for _attempt in range(1, self.retry_attempts + 1):
            try:
                response = httpx.get(self.base_url, headers=HEADERS, timeout=self.timeout_seconds, verify=self.verify_ssl)
                response.raise_for_status()
                realtime_records = parse_twport_realtime_wind_records(response.text)
                if parse_gridview1 is None:
                    rows = []
                else:
                    rows = parse_gridview1(response.text)
                self._cached_rows = rows
                self._cached_realtime_records = realtime_records
                self._cache_time = now
                return rows
            except Exception as exc:
                last_error = exc
                self._last_error = str(exc)
        raise RuntimeError(f"TWPort port-local fetch failed: {last_error}")

    def _normalize_rows(self, rows: list[dict[str, Any]], fetched_at: datetime) -> list[dict[str, Any]]:
        if normalize_row is None:
            return rows
        out = []
        for row in rows:
            observation = normalize_row(row, fetched_at=fetched_at)
            if observation is None:
                continue
            record = observation.to_dict() if hasattr(observation, "to_dict") else dict(observation)
            record["raw_data"] = getattr(observation, "raw_data", record.get("raw_data", {}))
            record["obs_time"] = getattr(observation, "obs_time", None)
            record["fetched_at"] = getattr(observation, "fetched_at", None)
            out.append(record)
        return out


def _matches_station(record: dict[str, Any], station_id: str) -> bool:
    candidates = {
        str(record.get("station_id", "")),
        str(record.get("station", {}).get("station_id", "")) if isinstance(record.get("station"), dict) else "",
        str(record.get("OriginalStationID9", "")),
        str(record.get("TableName", "")),
        str(record.get("ID", "")),
        str(record.get("raw_station_ref", "")),
    }
    return station_id in candidates or any(candidate.startswith(station_id) for candidate in candidates if candidate)
