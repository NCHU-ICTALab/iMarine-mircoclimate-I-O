from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo
import httpx

logger = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")

def parse_iso_datetime(val: str) -> datetime:
    """Parse ISO8601 string and convert to Taipei timezone-aware datetime."""
    # Handle space instead of T, and tailing Z or timezone offsets
    clean = val.strip().replace(" ", "T")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TAIPEI)
    return dt.astimezone(TAIPEI)

class CWAClient:
    def __init__(self, api_key: str, timeout: float = 15.0, verify_ssl: bool = False):
        self.api_key = api_key
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

    async def fetch_forecast_raw(self) -> dict[str, Any]:
        """Fetch general 36h weather forecast (F-C0032-001) which contains PoP."""
        if not self.api_key:
            raise ValueError("CWA_API_KEY is not configured")
        
        url = f"{self.base_url}/F-C0032-001"
        params = {
            "Authorization": self.api_key,
            "format": "JSON"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl) as client:
            logger.info("Fetching CWA Rain Forecast from %s", url)
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_observations_raw(self) -> dict[str, Any]:
        """Fetch rainfall station observations (O-A0002-001)."""
        if not self.api_key:
            raise ValueError("CWA_API_KEY is not configured")
        
        url = f"{self.base_url}/O-A0002-001"
        params = {
            "Authorization": self.api_key,
            "format": "JSON"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl) as client:
            logger.info("Fetching CWA Rain Observations from %s", url)
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get_forecasts(self, target_locations: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """Fetch and parse forecasts containing Probability of Precipitation (PoP)."""
        try:
            data = await self.fetch_forecast_raw()
            records = data.get("records", {})
            locations = records.get("location", [])
            
            parsed_forecasts = []
            for loc in locations:
                location_name = loc.get("locationName", "Unknown")
                if target_locations and location_name not in target_locations:
                    continue
                    
                weather_elements = loc.get("weatherElement", [])
                
                # Find PoP (Probability of Precipitation) and Wx (Weather Phenomenon)
                pop_element = None
                wx_element = None
                for elem in weather_elements:
                    elem_name = elem.get("elementName")
                    if elem_name == "PoP":
                        pop_element = elem
                    elif elem_name == "Wx":
                        wx_element = elem
                
                if not pop_element:
                    continue
                
                # Zip pop and wx by time slots (they have identical time structures)
                times = pop_element.get("time", [])
                wx_times = wx_element.get("time", []) if wx_element else []
                
                for idx, t_entry in enumerate(times):
                    start_str = t_entry.get("startTime")
                    end_str = t_entry.get("endTime")
                    pop_val_str = t_entry.get("parameter", {}).get("parameterName", "0")
                    
                    try:
                        pop_val = float(pop_val_str)
                    except ValueError:
                        pop_val = 0.0
                        
                    wx_val = "未知"
                    if idx < len(wx_times):
                        wx_val = wx_times[idx].get("parameter", {}).get("parameterName", "未知")
                    
                    parsed_forecasts.append({
                        "location_name": location_name,
                        "start_time": parse_iso_datetime(start_str).isoformat(),
                        "end_time": parse_iso_datetime(end_str).isoformat(),
                        "pop": pop_val,
                        "wx_phenomenon": wx_val
                    })
            return parsed_forecasts
        except Exception as exc:
            logger.exception("Error parsing CWA forecasts")
            raise exc

    async def get_observations(self, target_stations: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """Fetch and parse current rainfall observations."""
        try:
            data = await self.fetch_observations_raw()
            records = data.get("records", {})
            # CWA O-A0002-001 structure has 'station' (or 'location' in older/alternative endpoints)
            stations = records.get("station", records.get("location", []))
            
            parsed_obs = []
            for s in stations:
                station_name = s.get("StationName") or s.get("locationName")
                station_id = s.get("StationId") or s.get("stationId")
                
                if target_stations and station_id not in target_stations:
                    continue
                    
                # Check obs time
                obs_time_str = s.get("ObsTime") or s.get("DateTime") or s.get("time", {}).get("obsTime")
                if not obs_time_str:
                    continue
                    
                obs_time = parse_iso_datetime(obs_time_str)
                
                # GeoInfo
                geo = s.get("GeoInfo", {})
                coords = geo.get("Coordinates", [{}])[0] if geo.get("Coordinates") else {}
                latitude = coords.get("StationLatitude") or s.get("latitude")
                longitude = coords.get("StationLongitude") or s.get("longitude")
                elevation = geo.get("StationAltitude") or s.get("elevation")
                
                # Admin areas
                county = geo.get("CountyName") or s.get("parameter", {}).get("countyName")
                town = geo.get("TownName") or s.get("parameter", {}).get("townName")
                
                # Rainfall values
                rainfall_elem = s.get("RainfallElement", {})
                
                # Extract values
                precip_now = self._extract_precip(rainfall_elem.get("Now", {}))
                precip_1hr = self._extract_precip(rainfall_elem.get("Past1hr", {}))
                precip_24hr = self._extract_precip(rainfall_elem.get("Past24hr", {}))
                
                parsed_obs.append({
                    "station_id": station_id,
                    "station_name": station_name,
                    "county": county,
                    "town": town,
                    "obs_time": obs_time.isoformat(),
                    "latitude": float(latitude) if latitude is not None else None,
                    "longitude": float(longitude) if longitude is not None else None,
                    "elevation": float(elevation) if elevation is not None else None,
                    "precipitation_now": precip_now,
                    "precipitation_1hr": precip_1hr,
                    "precipitation_24hr": precip_24hr
                })
            return parsed_obs
        except Exception as exc:
            logger.exception("Error parsing CWA rainfall observations")
            raise exc

    def _extract_precip(self, val_dict: Any) -> float | None:
        if not isinstance(val_dict, dict):
            return None
        val = val_dict.get("Precipitation")
        if val in (None, "", "-", "-99", "-999", "NaN"):
            return None
        try:
            return float(val)
        except ValueError:
            return None

    async def get_qpf(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Fetch QPESUMS 1-hour QPF grid data (F-B0046-001) and find nearest prediction."""
        if not self.api_key:
            raise ValueError("CWA_API_KEY is not configured")
        
        url = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-B0046-001"
        params = {
            "Authorization": self.api_key,
            "format": "JSON"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl) as client:
                logger.info("Fetching CWA 1-hour QPF Grid from %s", url)
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            cwa_data = data.get("cwaopendata", {})
            dataset = cwa_data.get("dataset", {})
            dataset_info = dataset.get("datasetInfo", {})
            parameter_set = dataset_info.get("parameterSet", {})
            
            # Read metadata
            start_lon = float(parameter_set.get("StartPointLongitude", 118.0))
            start_lat = float(parameter_set.get("StartPointLatitude", 20.0))
            resolution = float(parameter_set.get("GridResolution", 0.0125))
            dim_x = int(parameter_set.get("GridDimensionX", 441))
            dim_y = int(parameter_set.get("GridDimensionY", 561))
            obs_time_str = parameter_set.get("DateTime")
            
            if not obs_time_str:
                obs_time_str = cwa_data.get("sent", datetime.now(TAIPEI).isoformat())
            
            obs_time = datetime.fromisoformat(obs_time_str)
            
            content_str = dataset.get("contents", {}).get("content", "")
            if not content_str:
                return None
                
            vals = [float(x) for x in content_str.split(",") if x.strip()]
            if len(vals) != dim_x * dim_y:
                logger.error("QPF grid dimension mismatch: expected %d values, got %d", dim_x * dim_y, len(vals))
                return None
                
            c = int(round((lon - start_lon) / resolution))
            r = int(round((lat - start_lat) / resolution))
            
            if 0 <= c < dim_x and 0 <= r < dim_y:
                idx = r * dim_x + c
                val = vals[idx]
                if val < 0:
                    val = 0.0
                return {
                    "obs_time": obs_time.isoformat(),
                    "latitude": lat,
                    "longitude": lon,
                    "qpf_1hr_mm": val
                }
            else:
                logger.warning("Target coordinates (lat=%f, lon=%f) are out of QPF grid bounds", lat, lon)
                return None
                
        except Exception:
            logger.exception("Error fetching/parsing QPF grid data")
            return None

