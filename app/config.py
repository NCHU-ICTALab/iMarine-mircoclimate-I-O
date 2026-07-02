from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "microclimate.sqlite3")
    twport_base_url: str = os.getenv(
        "TWPORT_BASE_URL",
        "https://wwtf.twport.com.tw/twport/display/Realtime_Panel_Port_GatData_2024.aspx",
    )
    twport_port_id: int = int(os.getenv("TWPORT_PORT_ID", "5"))
    twport_verify_ssl: bool = os.getenv("TWPORT_VERIFY_SSL", "true").lower() == "true"
    cwa_api_key: str = os.getenv("CWA_API_KEY", "")
    cwa_data_id: str = os.getenv("CWA_DATA_ID", "O-A0001-001")
    cwa_station_names: str = os.getenv("CWA_STATION_NAMES", "高雄,小港,旗后,高雄港")
    cwa_county_names: str = os.getenv("CWA_COUNTY_NAMES", "高雄市")
    cwa_history_data_id: str = os.getenv("CWA_HISTORY_DATA_ID", "O-A0001-001")
    cwa_history_stations: str = os.getenv("CWA_HISTORY_STATIONS", "467441:cwb:Kaohsiung")
    cwa_marine_data_id: str = os.getenv("CWA_MARINE_DATA_ID", "O-B0075-001")
    cwa_marine_station_ids: str = os.getenv("CWA_MARINE_STATION_IDS", "C4P01,1786,COMC08,46714D,C4Q02,C4Q01")
    cwa_verify_ssl: bool = os.getenv("CWA_VERIFY_SSL", "true").lower() == "true"
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
    alert_wind_speed: float = float(os.getenv("ALERT_WIND_SPEED", "13.8"))
    alert_wind_gust: float = float(os.getenv("ALERT_WIND_GUST", "17.2"))

    @property
    def database_path(self) -> Path:
        return Path(self.database_url)

    @property
    def cwa_station_name_list(self) -> list[str]:
        return [item.strip() for item in self.cwa_station_names.split(",") if item.strip()]

    @property
    def cwa_county_name_list(self) -> list[str]:
        return [item.strip() for item in self.cwa_county_names.split(",") if item.strip()]

    @property
    def cwa_history_station_specs(self) -> list[dict[str, str]]:
        specs = []
        for item in self.cwa_history_stations.split(","):
            parts = [part.strip() for part in item.split(":")]
            if not parts or not parts[0]:
                continue
            specs.append(
                {
                    "station_id": parts[0],
                    "station_type": parts[1] if len(parts) > 1 and parts[1] else "cwb",
                    "station_name": parts[2] if len(parts) > 2 and parts[2] else parts[0],
                }
            )
        return specs

    @property
    def cwa_marine_station_id_list(self) -> list[str]:
        return [item.strip() for item in self.cwa_marine_station_ids.split(",") if item.strip()]


settings = Settings()
