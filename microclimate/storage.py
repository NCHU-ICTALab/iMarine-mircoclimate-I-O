from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .models import Observation, UTC, ensure_utc


SCHEMA = """
CREATE TABLE IF NOT EXISTS microclimate_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    station_name TEXT NOT NULL,
    obs_time TEXT NOT NULL,
    source TEXT NOT NULL,
    wind_speed REAL,
    wind_gust REAL,
    wind_direction REAL,
    precipitation_10min REAL,
    precipitation_1hr REAL,
    visibility REAL,
    tide_level REAL,
    wave_height REAL,
    is_forecast INTEGER NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL DEFAULT 'high',
    fetched_at TEXT NOT NULL,
    UNIQUE(station_id, obs_time, source, is_forecast)
);
CREATE INDEX IF NOT EXISTS idx_microclimate_latest
ON microclimate_observations (is_forecast, source, station_id, obs_time DESC);
"""


class ObservationStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_many(self, observations: list[Observation]) -> int:
        if not observations:
            return 0
        rows = [obs.normalized() for obs in observations]
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO microclimate_observations (
                    station_id, station_name, obs_time, source,
                    wind_speed, wind_gust, wind_direction,
                    precipitation_10min, precipitation_1hr, visibility,
                    tide_level, wave_height, is_forecast, confidence, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id, obs_time, source, is_forecast) DO UPDATE SET
                    station_name=excluded.station_name,
                    wind_speed=excluded.wind_speed,
                    wind_gust=excluded.wind_gust,
                    wind_direction=excluded.wind_direction,
                    precipitation_10min=excluded.precipitation_10min,
                    precipitation_1hr=excluded.precipitation_1hr,
                    visibility=excluded.visibility,
                    tide_level=excluded.tide_level,
                    wave_height=excluded.wave_height,
                    confidence=excluded.confidence,
                    fetched_at=excluded.fetched_at
                """,
                [
                    (
                        obs.station_id,
                        obs.station_name,
                        obs.obs_time.isoformat(),
                        obs.source,
                        obs.wind_speed,
                        obs.wind_gust,
                        obs.wind_direction,
                        obs.precipitation_10min,
                        obs.precipitation_1hr,
                        obs.visibility,
                        obs.tide_level,
                        obs.wave_height,
                        int(obs.is_forecast),
                        obs.confidence,
                        obs.fetched_at.isoformat() if obs.fetched_at else datetime.now(UTC).isoformat(),
                    )
                    for obs in rows
                ],
            )
        return len(rows)

    def latest_observations(self, include_forecast: bool = False) -> list[Observation]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM microclimate_observations m
                WHERE is_forecast = ?
                  AND obs_time = (
                    SELECT MAX(obs_time)
                    FROM microclimate_observations
                    WHERE station_id = m.station_id
                      AND source = m.source
                      AND is_forecast = m.is_forecast
                  )
                ORDER BY CASE source WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END, obs_time DESC
                """,
                (int(include_forecast),),
            ).fetchall()
        return [row_to_observation(row) for row in rows]

    def recent_history(self, hours: int = 2) -> list[Observation]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM microclimate_observations
                WHERE is_forecast = 0 AND obs_time >= ?
                ORDER BY source, station_id, obs_time
                """,
                (since.isoformat(),),
            ).fetchall()
        return [row_to_observation(row) for row in rows]

    def prune_older_than(self, hours: int = 3) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM microclimate_observations WHERE is_forecast = 0 AND obs_time < ?",
                (cutoff.isoformat(),),
            )
            return cursor.rowcount


def row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(
        station_id=row["station_id"],
        station_name=row["station_name"],
        obs_time=datetime.fromisoformat(row["obs_time"]),
        source=row["source"],
        wind_speed=row["wind_speed"],
        wind_gust=row["wind_gust"],
        wind_direction=row["wind_direction"],
        precipitation_10min=row["precipitation_10min"],
        precipitation_1hr=row["precipitation_1hr"],
        visibility=row["visibility"],
        tide_level=row["tide_level"],
        wave_height=row["wave_height"],
        is_forecast=bool(row["is_forecast"]),
        confidence=row["confidence"],
        fetched_at=ensure_utc(datetime.fromisoformat(row["fetched_at"])),
    )
