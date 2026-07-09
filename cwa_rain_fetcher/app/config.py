from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    cwa_api_key: str = os.getenv("CWA_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "rain_data.sqlite3")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8010"))
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"
    cwa_verify_ssl: bool = os.getenv("CWA_VERIFY_SSL", "False").lower() == "true"
    
    # Auto-Sync configuration
    auto_sync_enabled: bool = os.getenv("AUTO_SYNC_ENABLED", "True").lower() == "true"
    auto_sync_interval_seconds: int = int(os.getenv("AUTO_SYNC_INTERVAL_SECONDS", "1800"))
    
    # Filtering settings (defaults to Kaohsiung Port area)
    # C0V890 (Qianzhen/旗津), C0V490 (Gushan/鼓山), C0V810 (Zuoying/左營), C0V840 (Xiaogang/小港), 
    # C0V450 (Xiaogang Outer/過港), C0V900 (Linyuan/林園), 467441 (Kaohsiung Station)
    target_station_ids: tuple[str, ...] = tuple(
        os.getenv("TARGET_STATION_IDS", "C0V890,C0V490,C0V810,C0V840,C0V450,C0V900,467441").split(",")
    )
    target_forecast_locations: tuple[str, ...] = tuple(
        os.getenv("TARGET_FORECAST_LOCATIONS", "高雄市").split(",")
    )
    target_latitude: float = float(os.getenv("TARGET_LATITUDE", "22.62"))
    target_longitude: float = float(os.getenv("TARGET_LONGITUDE", "120.28"))

    
    @property
    def database_path(self) -> Path:
        # Resolve path relative to project root
        proj_root = Path(__file__).resolve().parents[1]
        path = Path(self.database_url)
        if not path.is_absolute():
            return proj_root / path
        return path

settings = Settings()

