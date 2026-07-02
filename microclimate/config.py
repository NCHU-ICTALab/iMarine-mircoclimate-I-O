from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    cwa_api_key: str = os.getenv("CWA_API_KEY", "")
    cwa_data_id: str = os.getenv("CWA_DATA_ID", "O-A0001-001")
    cwa_station_names: list[str] = None  # type: ignore[assignment]
    twport_api_url: str = os.getenv("TWPORT_API_URL", "")
    twport_station_names: list[str] = None  # type: ignore[assignment]
    database_url: str = os.getenv("DATABASE_URL", "microclimate.sqlite3")
    fetch_on_startup: bool = os.getenv("FETCH_ON_STARTUP", "false").lower() == "true"
    alert_wind_speed: float = float(os.getenv("ALERT_WIND_SPEED", "13.8"))
    alert_wind_gust: float = float(os.getenv("ALERT_WIND_GUST", "17.2"))
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cwa_station_names",
            _csv_env("CWA_STATION_NAMES", "高雄,小港,旗后,高雄港"),
        )
        object.__setattr__(
            self,
            "twport_station_names",
            _csv_env("TWPORT_STATION_NAMES", "高雄港,旗津,中島"),
        )

    @property
    def database_path(self) -> Path:
        return Path(self.database_url)


settings = Settings()
