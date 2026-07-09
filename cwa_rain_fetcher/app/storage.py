from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cwa_rain_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    pop REAL NOT NULL,
    wx_phenomenon TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(location_name, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS cwa_rain_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    station_name TEXT NOT NULL,
    county TEXT,
    town TEXT,
    obs_time TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    elevation REAL,
    precipitation_now REAL,
    precipitation_1hr REAL,
    precipitation_24hr REAL,
    fetched_at TEXT NOT NULL,
    UNIQUE(station_id, obs_time)
);

CREATE TABLE IF NOT EXISTS cwa_rain_qpf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_time TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    qpf_1hr_mm REAL,
    fetched_at TEXT NOT NULL,
    UNIQUE(obs_time, latitude, longitude)
);

CREATE INDEX IF NOT EXISTS idx_forecast_location ON cwa_rain_forecasts(location_name);
CREATE INDEX IF NOT EXISTS idx_forecast_time ON cwa_rain_forecasts(start_time);
CREATE INDEX IF NOT EXISTS idx_observation_station ON cwa_rain_observations(station_id);
CREATE INDEX IF NOT EXISTS idx_observation_time ON cwa_rain_observations(obs_time);
CREATE INDEX IF NOT EXISTS idx_observation_county ON cwa_rain_observations(county);
CREATE INDEX IF NOT EXISTS idx_qpf_time ON cwa_rain_qpf(obs_time);

"""

class RainStorage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def save_forecasts(self, forecasts: list[dict[str, Any]]) -> int:
        if not forecasts:
            return 0
            
        fetched_at = datetime.now(TAIPEI).isoformat()
        inserted = 0
        with self.connect() as conn:
            for item in forecasts:
                try:
                    conn.execute(
                        """
                        INSERT INTO cwa_rain_forecasts (
                            location_name, start_time, end_time, pop, wx_phenomenon, fetched_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(location_name, start_time, end_time) DO UPDATE SET
                            pop=excluded.pop,
                            wx_phenomenon=excluded.wx_phenomenon,
                            fetched_at=excluded.fetched_at
                        """,
                        (
                            item["location_name"],
                            item["start_time"],
                            item["end_time"],
                            item["pop"],
                            item["wx_phenomenon"],
                            fetched_at
                        )
                    )
                    inserted += 1
                except sqlite3.Error:
                    continue
        return inserted

    def save_observations(self, obs: list[dict[str, Any]]) -> int:
        if not obs:
            return 0
            
        fetched_at = datetime.now(TAIPEI).isoformat()
        inserted = 0
        with self.connect() as conn:
            for item in obs:
                try:
                    conn.execute(
                        """
                        INSERT INTO cwa_rain_observations (
                            station_id, station_name, county, town, obs_time,
                            latitude, longitude, elevation, precipitation_now,
                            precipitation_1hr, precipitation_24hr, fetched_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(station_id, obs_time) DO UPDATE SET
                            precipitation_now=excluded.precipitation_now,
                            precipitation_1hr=excluded.precipitation_1hr,
                            precipitation_24hr=excluded.precipitation_24hr,
                            fetched_at=excluded.fetched_at
                        """,
                        (
                            item["station_id"],
                            item["station_name"],
                            item["county"],
                            item["town"],
                            item["obs_time"],
                            item["latitude"],
                            item["longitude"],
                            item["elevation"],
                            item["precipitation_now"],
                            item["precipitation_1hr"],
                            item["precipitation_24hr"],
                            fetched_at
                        )
                    )
                    inserted += 1
                except sqlite3.Error:
                    continue
        return inserted

    def get_latest_forecasts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get the latest forecasts for each location."""
        with self.connect() as conn:
            # First, find the maximum start_time currently available
            rows = conn.execute(
                """
                SELECT f.*
                FROM cwa_rain_forecasts f
                INNER JOIN (
                    SELECT location_name, MAX(start_time) as max_start
                    FROM cwa_rain_forecasts
                    GROUP BY location_name
                ) group_max ON f.location_name = group_max.location_name AND f.start_time = group_max.max_start
                ORDER BY f.location_name
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_forecasts_for_location(self, location_name: str, limit: int = 12) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cwa_rain_forecasts
                WHERE location_name = ?
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (location_name, limit)
            ).fetchall()
            # Sort chronologically for charts
            res = [dict(row) for row in rows]
            res.reverse()
            return res

    def get_latest_observations(self, county: str | None = None, limit: int = 150) -> list[dict[str, Any]]:
        with self.connect() as conn:
            query = """
                SELECT o.*
                FROM cwa_rain_observations o
                INNER JOIN (
                    SELECT station_id, MAX(obs_time) as max_obs
                    FROM cwa_rain_observations
                    GROUP BY station_id
                ) group_max ON o.station_id = group_max.station_id AND o.obs_time = group_max.max_obs
            """
            params = []
            if county:
                query += " WHERE o.county LIKE ?"
                params.append(f"%{county}%")
                
            query += " ORDER BY o.precipitation_24hr DESC, o.precipitation_1hr DESC, o.station_name LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_station_history(self, station_id: str, limit: int = 24) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cwa_rain_observations
                WHERE station_id = ?
                ORDER BY obs_time DESC
                LIMIT ?
                """,
                (station_id, limit)
            ).fetchall()
            res = [dict(row) for row in rows]
            res.reverse()
            return res

    def save_qpf(self, qpf_data: dict[str, Any]) -> int:
        if not qpf_data:
            return 0
        fetched_at = datetime.now(TAIPEI).isoformat()
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO cwa_rain_qpf (
                        obs_time, latitude, longitude, qpf_1hr_mm, fetched_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(obs_time, latitude, longitude) DO UPDATE SET
                        qpf_1hr_mm=excluded.qpf_1hr_mm,
                        fetched_at=excluded.fetched_at
                    """,
                    (
                        qpf_data["obs_time"],
                        qpf_data["latitude"],
                        qpf_data["longitude"],
                        qpf_data["qpf_1hr_mm"],
                        fetched_at
                    )
                )
                return 1
            except sqlite3.Error:
                return 0

    def get_latest_qpf(self, latitude: float, longitude: float, limit: int = 12) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cwa_rain_qpf
                WHERE ABS(latitude - ?) < 0.05 AND ABS(longitude - ?) < 0.05
                ORDER BY obs_time DESC
                LIMIT ?
                """,
                (latitude, longitude, limit)
            ).fetchall()
            res = [dict(row) for row in rows]
            res.reverse()
            return res

    def get_db_stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            fc_count = conn.execute("SELECT COUNT(*) FROM cwa_rain_forecasts").fetchone()[0]
            obs_count = conn.execute("SELECT COUNT(*) FROM cwa_rain_observations").fetchone()[0]
            qpf_count = conn.execute("SELECT COUNT(*) FROM cwa_rain_qpf").fetchone()[0]
            latest_fc = conn.execute("SELECT MAX(fetched_at) FROM cwa_rain_forecasts").fetchone()[0]
            latest_obs = conn.execute("SELECT MAX(fetched_at) FROM cwa_rain_observations").fetchone()[0]
            latest_qpf = conn.execute("SELECT MAX(fetched_at) FROM cwa_rain_qpf").fetchone()[0]
            return {
                "forecast_total_rows": fc_count,
                "observation_total_rows": obs_count,
                "qpf_total_rows": qpf_count,
                "last_forecast_sync": latest_fc,
                "last_observation_sync": latest_obs,
                "last_qpf_sync": latest_qpf
            }

