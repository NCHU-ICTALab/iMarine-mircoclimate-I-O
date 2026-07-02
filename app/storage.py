from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models import TAIPEI, TwPortObservation


SCHEMA = """
CREATE TABLE IF NOT EXISTS microclimate_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    port_code TEXT,
    station_id TEXT NOT NULL,
    station_name TEXT NOT NULL,
    location TEXT,
    device_type TEXT NOT NULL,
    obs_time TEXT NOT NULL,
    longitude REAL,
    latitude REAL,
    elevation REAL,
    wind_speed REAL,
    wind_gust REAL,
    wind_direction REAL,
    wind_gust_direction REAL,
    precipitation_10min REAL,
    precipitation_1hr REAL,
    precipitation_24hr REAL,
    air_temperature REAL,
    relative_humidity REAL,
    air_pressure REAL,
    visibility REAL,
    tide_level REAL,
    tide_level_unit TEXT,
    wave_height REAL,
    wave_period REAL,
    wave_max_height REAL,
    current_speed REAL,
    current_direction REAL,
    raw_data TEXT NOT NULL DEFAULT '{}',
    raw_last_data_str TEXT,
    is_forecast INTEGER NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL DEFAULT 'high',
    stale INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL,
    UNIQUE(source, station_id, device_type, obs_time, is_forecast)
);
CREATE INDEX IF NOT EXISTS idx_obs_station_id ON microclimate_observations(station_id);
CREATE INDEX IF NOT EXISTS idx_obs_obs_time ON microclimate_observations(obs_time);
CREATE INDEX IF NOT EXISTS idx_obs_device_type ON microclimate_observations(device_type);
CREATE INDEX IF NOT EXISTS idx_obs_source ON microclimate_observations(source);
"""


DEFAULT_STATUS_POLICY = {
    "threshold_minutes": 20,
    "expected_update_interval": "約 5-20 分鐘",
    "note": "未指定類型時使用保守門檻。",
}

DATA_STATUS_POLICIES = {
    ("twport", "WIND"): {
        "threshold_minutes": 20,
        "expected_update_interval": "現場風站約 1-5 分鐘；模擬風站可能整點更新",
        "note": "風速對港口作業影響高，維持較嚴格門檻。",
    },
    ("twport", "VISIBILITY"): {
        "threshold_minutes": 20,
        "expected_update_interval": "約 1-5 分鐘",
        "note": "能見度屬即時安全條件，維持較嚴格門檻。",
    },
    ("twport", "TIDE"): {
        "threshold_minutes": 75,
        "expected_update_interval": "主站約數分鐘；模擬站常見整點更新",
        "note": "潮位與模擬資料更新頻率不同，採較寬門檻。",
    },
    ("twport", "WAVE"): {
        "threshold_minutes": 75,
        "expected_update_interval": "多為整點或約 1 小時",
        "note": "波浪模擬資料通常不是分鐘級更新。",
    },
    ("twport", "CURRENT"): {
        "threshold_minutes": 75,
        "expected_update_interval": "多為整點或約 1 小時",
        "note": "海流模擬資料通常不是分鐘級更新。",
    },
    ("twport", "AWAC"): {
        "threshold_minutes": 90,
        "expected_update_interval": "約 30-60 分鐘",
        "note": "底碇式波流觀測站常有較長更新間隔。",
    },
    ("twport", "STABILITY"): {
        "threshold_minutes": 75,
        "expected_update_interval": "多為整點或約 1 小時",
        "note": "港內靜穩資料常見整點更新。",
    },
    ("cwa", "WEATHER"): {
        "threshold_minutes": 75,
        "expected_update_interval": "約每 1 小時",
        "note": "CWA 自動站資料常以整點或接近整點更新。",
    },
}

OUTAGE_AFTER_MINUTES = 24 * 60


class ObservationStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self.ensure_columns(conn)

    def ensure_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(microclimate_observations)").fetchall()
        }
        columns = {
            "precipitation_10min": "REAL",
            "precipitation_1hr": "REAL",
            "precipitation_24hr": "REAL",
            "air_temperature": "REAL",
            "relative_humidity": "REAL",
            "air_pressure": "REAL",
        }
        for name, column_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE microclimate_observations ADD COLUMN {name} {column_type}")

    def upsert_many(self, observations: list[TwPortObservation]) -> int:
        if not observations:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO microclimate_observations (
                    source, port_code, station_id, station_name, location, device_type, obs_time,
                    longitude, latitude, elevation, wind_speed, wind_gust, wind_direction,
                    wind_gust_direction, precipitation_10min, precipitation_1hr, precipitation_24hr,
                    air_temperature, relative_humidity, air_pressure, visibility,
                    tide_level, tide_level_unit, wave_height,
                    wave_period, wave_max_height, current_speed, current_direction, raw_data,
                    raw_last_data_str, is_forecast, confidence, stale, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, station_id, device_type, obs_time, is_forecast) DO UPDATE SET
                    station_name=excluded.station_name,
                    location=excluded.location,
                    wind_speed=excluded.wind_speed,
                    wind_gust=excluded.wind_gust,
                    wind_direction=excluded.wind_direction,
                    wind_gust_direction=excluded.wind_gust_direction,
                    precipitation_10min=excluded.precipitation_10min,
                    precipitation_1hr=excluded.precipitation_1hr,
                    precipitation_24hr=excluded.precipitation_24hr,
                    air_temperature=excluded.air_temperature,
                    relative_humidity=excluded.relative_humidity,
                    air_pressure=excluded.air_pressure,
                    visibility=excluded.visibility,
                    tide_level=excluded.tide_level,
                    wave_height=excluded.wave_height,
                    wave_period=excluded.wave_period,
                    wave_max_height=excluded.wave_max_height,
                    current_speed=excluded.current_speed,
                    current_direction=excluded.current_direction,
                    raw_data=excluded.raw_data,
                    raw_last_data_str=excluded.raw_last_data_str,
                    confidence=excluded.confidence,
                    stale=excluded.stale,
                    fetched_at=excluded.fetched_at
                """,
                [observation_to_row(obs) for obs in observations],
            )
        return len(observations)

    def latest_by_device_type(self) -> list[TwPortObservation]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM microclimate_observations m
                WHERE obs_time = (
                    SELECT MAX(obs_time)
                    FROM microclimate_observations
                    WHERE device_type = m.device_type
                      AND station_id = m.station_id
                      AND is_forecast = 0
                )
                ORDER BY device_type, station_id
                """
            ).fetchall()
        return [row_to_observation(row) for row in rows]

    def data_status(self, stale_after_minutes: int | None = None) -> dict[str, Any]:
        now = datetime.now(TAIPEI)
        latest_observations = self.latest_by_source_station_device()

        with self.connect() as conn:
            summary_rows = conn.execute(
                """
                SELECT
                    source,
                    device_type,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT station_id) AS station_count,
                    MAX(obs_time) AS latest_obs_time,
                    MAX(fetched_at) AS latest_fetched_at,
                    SUM(stale) AS stored_stale_count
                FROM microclimate_observations
                WHERE is_forecast = 0
                GROUP BY source, device_type
                ORDER BY source, device_type
                """
            ).fetchall()
            total_rows = int(
                conn.execute(
                    "SELECT COUNT(*) FROM microclimate_observations WHERE is_forecast = 0"
                ).fetchone()[0]
            )

        station_items = [observation_status(obs, now, stale_after_minutes) for obs in latest_observations]
        station_items.sort(key=lambda item: (item["source"], item["device_type"], item["station_name"]))

        station_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in station_items:
            station_groups.setdefault((item["source"], item["device_type"]), []).append(item)

        groups: list[dict[str, Any]] = []
        for row in summary_rows:
            latest_obs_time = parse_optional_datetime(row["latest_obs_time"])
            latest_fetched_at = parse_optional_datetime(row["latest_fetched_at"])
            group_stations = station_groups.get((row["source"], row["device_type"]), [])
            policy = status_policy(row["source"], row["device_type"], stale_after_minutes)
            current_stale_count = sum(1 for item in group_stations if item["is_stale_now"])
            outage_count = sum(1 for item in group_stations if item["status_level"] == "outage")
            groups.append(
                {
                    "source": row["source"],
                    "device_type": row["device_type"],
                    "threshold_minutes": policy["threshold_minutes"],
                    "expected_update_interval": policy["expected_update_interval"],
                    "policy_note": policy["note"],
                    "row_count": int(row["row_count"]),
                    "station_count": int(row["station_count"]),
                    "latest_station_count": len(group_stations),
                    "latest_obs_time": format_optional_datetime(latest_obs_time),
                    "latest_fetched_at": format_optional_datetime(latest_fetched_at),
                    "latest_obs_age_minutes": age_minutes(latest_obs_time, now),
                    "latest_fetch_age_minutes": age_minutes(latest_fetched_at, now),
                    "stored_stale_count": int(row["stored_stale_count"] or 0),
                    "current_stale_count": current_stale_count,
                    "outage_count": outage_count,
                    "is_current": bool(group_stations) and current_stale_count == 0,
                }
            )

        latest_obs_times = [
            parse_optional_datetime(row["latest_obs_time"])
            for row in summary_rows
            if row["latest_obs_time"]
        ]
        latest_fetched_times = [
            parse_optional_datetime(row["latest_fetched_at"])
            for row in summary_rows
            if row["latest_fetched_at"]
        ]
        latest_obs_time = max((item for item in latest_obs_times if item), default=None)
        latest_fetched_at = max((item for item in latest_fetched_times if item), default=None)
        current_stale_count = sum(1 for item in station_items if item["is_stale_now"])

        return {
            "generated_at": now.isoformat(),
            "stale_after_minutes": stale_after_minutes,
            "status_policies": serialize_status_policies(stale_after_minutes),
            "overall": {
                "is_current": bool(station_items) and current_stale_count == 0,
                "total_rows": total_rows,
                "latest_station_count": len(station_items),
                "current_stale_count": current_stale_count,
                "source_count": len({item["source"] for item in station_items}),
                "device_type_count": len({item["device_type"] for item in station_items}),
                "latest_obs_time": format_optional_datetime(latest_obs_time),
                "latest_fetched_at": format_optional_datetime(latest_fetched_at),
                "latest_obs_age_minutes": age_minutes(latest_obs_time, now),
                "latest_fetch_age_minutes": age_minutes(latest_fetched_at, now),
            },
            "groups": groups,
            "stations": station_items,
        }

    def latest_by_source_station_device(self) -> list[TwPortObservation]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM microclimate_observations m
                WHERE obs_time = (
                    SELECT MAX(obs_time)
                    FROM microclimate_observations
                    WHERE source = m.source
                      AND device_type = m.device_type
                      AND station_id = m.station_id
                      AND is_forecast = 0
                )
                  AND is_forecast = 0
                ORDER BY source, device_type, station_id
                """
            ).fetchall()
        return [row_to_observation(row) for row in rows]

    def recent_history(self, hours: int = 2) -> list[TwPortObservation]:
        cutoff = datetime.now(TAIPEI).timestamp() - hours * 3600
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM microclimate_observations
                WHERE is_forecast = 0
                ORDER BY station_id, device_type, obs_time
                """
            ).fetchall()
        observations = [row_to_observation(row) for row in rows]
        return [obs for obs in observations if obs.obs_time.timestamp() >= cutoff]

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM microclimate_observations").fetchone()[0])

    def latest_fetched_at(self) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(fetched_at) FROM microclimate_observations").fetchone()
        return row[0] if row and row[0] else None


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(TAIPEI)


def format_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(TAIPEI).isoformat()


def age_minutes(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    return max(0, int((now - value.astimezone(TAIPEI)).total_seconds() // 60))


def status_policy(
    source: str, device_type: str, stale_after_minutes: int | None = None
) -> dict[str, Any]:
    if stale_after_minutes is not None:
        return {
            **DEFAULT_STATUS_POLICY,
            "threshold_minutes": stale_after_minutes,
            "note": "呼叫端指定單一過期門檻。",
        }
    policy = DATA_STATUS_POLICIES.get(
        (source.lower(), device_type.upper()),
        DATA_STATUS_POLICIES.get((source.lower(), device_type), DEFAULT_STATUS_POLICY),
    )
    return dict(policy)


def serialize_status_policies(stale_after_minutes: int | None = None) -> list[dict[str, Any]]:
    if stale_after_minutes is not None:
        return [
            {
                "source": "*",
                "device_type": "*",
                **status_policy("*", "*", stale_after_minutes),
            }
        ]
    return [
        {"source": source, "device_type": device_type, **policy}
        for (source, device_type), policy in sorted(DATA_STATUS_POLICIES.items())
    ]


def status_level(obs_age: int | None, threshold_minutes: int) -> tuple[str, str]:
    if obs_age is None:
        return "stale", "過期"
    if obs_age > OUTAGE_AFTER_MINUTES:
        return "outage", "停擺"
    if obs_age > threshold_minutes:
        return "stale", "過期"
    return "current", "正常"


def observation_status(
    obs: TwPortObservation, now: datetime, stale_after_minutes: int | None
) -> dict[str, Any]:
    obs_age = age_minutes(obs.obs_time, now)
    fetch_age = age_minutes(obs.fetched_at, now)
    policy = status_policy(obs.source, obs.device_type, stale_after_minutes)
    level, label = status_level(obs_age, int(policy["threshold_minutes"]))
    is_stale_now = level in {"stale", "outage"}
    return {
        "source": obs.source,
        "device_type": obs.device_type,
        "threshold_minutes": policy["threshold_minutes"],
        "expected_update_interval": policy["expected_update_interval"],
        "policy_note": policy["note"],
        "station_id": obs.station_id,
        "station_name": obs.station_name,
        "location": obs.location,
        "obs_time": obs.obs_time.astimezone(TAIPEI).isoformat(),
        "fetched_at": obs.fetched_at.astimezone(TAIPEI).isoformat() if obs.fetched_at else None,
        "obs_age_minutes": obs_age,
        "fetch_age_minutes": fetch_age,
        "stored_stale": obs.stale,
        "is_stale_now": is_stale_now,
        "status_level": level,
        "status_label": label,
    }


def observation_to_row(obs: TwPortObservation) -> tuple[Any, ...]:
    return (
        obs.source,
        obs.port_code,
        obs.station_id,
        obs.station_name,
        obs.location,
        obs.device_type,
        obs.obs_time.astimezone(TAIPEI).isoformat(),
        obs.longitude,
        obs.latitude,
        obs.elevation,
        obs.wind_speed,
        obs.wind_gust,
        obs.wind_direction,
        obs.wind_gust_direction,
        obs.precipitation_10min,
        obs.precipitation_1hr,
        obs.precipitation_24hr,
        obs.air_temperature,
        obs.relative_humidity,
        obs.air_pressure,
        obs.visibility,
        obs.tide_level,
        obs.tide_level_unit,
        obs.wave_height,
        obs.wave_period,
        obs.wave_max_height,
        obs.current_speed,
        obs.current_direction,
        json.dumps(obs.raw_data or {}, ensure_ascii=False),
        obs.raw_last_data_str,
        int(obs.is_forecast),
        obs.confidence,
        int(obs.stale),
        (obs.fetched_at or datetime.now(TAIPEI)).astimezone(TAIPEI).isoformat(),
    )


def row_to_observation(row: sqlite3.Row) -> TwPortObservation:
    return TwPortObservation(
        source=row["source"],
        port_code=row["port_code"],
        station_id=row["station_id"],
        station_name=row["station_name"],
        location=row["location"],
        device_type=row["device_type"],
        obs_time=datetime.fromisoformat(row["obs_time"]),
        longitude=row["longitude"],
        latitude=row["latitude"],
        elevation=row["elevation"],
        wind_speed=row["wind_speed"],
        wind_gust=row["wind_gust"],
        wind_direction=row["wind_direction"],
        wind_gust_direction=row["wind_gust_direction"],
        precipitation_10min=row["precipitation_10min"],
        precipitation_1hr=row["precipitation_1hr"],
        precipitation_24hr=row["precipitation_24hr"],
        air_temperature=row["air_temperature"],
        relative_humidity=row["relative_humidity"],
        air_pressure=row["air_pressure"],
        visibility=row["visibility"],
        tide_level=row["tide_level"],
        tide_level_unit=row["tide_level_unit"],
        wave_height=row["wave_height"],
        wave_period=row["wave_period"],
        wave_max_height=row["wave_max_height"],
        current_speed=row["current_speed"],
        current_direction=row["current_direction"],
        raw_data=json.loads(row["raw_data"] or "{}"),
        raw_last_data_str=row["raw_last_data_str"],
        is_forecast=bool(row["is_forecast"]),
        confidence=row["confidence"],
        stale=bool(row["stale"]),
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
    )
