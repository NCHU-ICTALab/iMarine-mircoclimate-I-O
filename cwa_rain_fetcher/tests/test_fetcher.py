import pytest
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

from app.cwa_client import CWAClient, parse_iso_datetime
from app.storage import RainStorage

TAIPEI = ZoneInfo("Asia/Taipei")

MOCK_FORECAST_JSON = {
    "success": "true",
    "records": {
        "datasetDescription": "一般天氣預報",
        "location": [
            {
                "locationName": "高雄市",
                "weatherElement": [
                    {
                        "elementName": "Wx",
                        "time": [
                            {
                                "startTime": "2026-07-09 18:00:00",
                                "endTime": "2026-07-10 06:00:00",
                                "parameter": {"parameterName": "多雲"}
                            }
                        ]
                    },
                    {
                        "elementName": "PoP",
                        "time": [
                            {
                                "startTime": "2026-07-09 18:00:00",
                                "endTime": "2026-07-10 06:00:00",
                                "parameter": {"parameterName": "30"}
                            }
                        ]
                    }
                ]
            }
        ]
    }
}

MOCK_OBSERVATIONS_JSON = {
    "success": "true",
    "records": {
        "station": [
            {
                "StationName": "旗津",
                "StationId": "C0V890",
                "ObsTime": "2026-07-09T22:00:00+08:00",
                "GeoInfo": {
                    "Coordinates": [{"StationLatitude": 22.6, "StationLongitude": 120.27, "StationAltitude": 5.0}],
                    "CountyName": "高雄市",
                    "TownName": "旗津區"
                },
                "RainfallElement": {
                    "Now": {"Precipitation": 0.5},
                    "Past1hr": {"Precipitation": 1.2},
                    "Past24hr": {"Precipitation": 5.5}
                }
            }
        ]
    }
}

def test_parse_iso_datetime():
    dt = parse_iso_datetime("2026-07-09 18:00:00")
    assert dt.tzinfo == TAIPEI
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 9
    assert dt.hour == 18

def test_client_get_forecasts():
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FORECAST_JSON
    mock_resp.raise_for_status = lambda: None
    
    mock_instance = AsyncMock()
    mock_instance.get.return_value = mock_resp
    
    with patch("app.cwa_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        client = CWAClient("dummy_key")
        # Match filter
        forecasts = asyncio.run(client.get_forecasts(target_locations=("高雄市",)))
        assert len(forecasts) == 1
        assert forecasts[0]["location_name"] == "高雄市"
        assert forecasts[0]["pop"] == 30.0
        assert forecasts[0]["wx_phenomenon"] == "多雲"
        
        # Mismatch filter
        forecasts_mismatch = asyncio.run(client.get_forecasts(target_locations=("臺北市",)))
        assert len(forecasts_mismatch) == 0

def test_client_get_observations():
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_OBSERVATIONS_JSON
    mock_resp.raise_for_status = lambda: None
    
    mock_instance = AsyncMock()
    mock_instance.get.return_value = mock_resp
    
    with patch("app.cwa_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        client = CWAClient("dummy_key")
        # Match filter
        obs = asyncio.run(client.get_observations(target_stations=("C0V890",)))
        assert len(obs) == 1
        assert obs[0]["station_id"] == "C0V890"
        assert obs[0]["station_name"] == "旗津"
        assert obs[0]["county"] == "高雄市"
        
        # Mismatch filter
        obs_mismatch = asyncio.run(client.get_observations(target_stations=("OTHER",)))
        assert len(obs_mismatch) == 0

def test_storage_operations(tmp_path):
    db_file = tmp_path / "test_rain.db"
    store = RainStorage(db_file)
    
    # Save dummy forecast
    forecasts = [{
        "location_name": "高雄市",
        "start_time": "2026-07-09T18:00:00+08:00",
        "end_time": "2026-07-10T06:00:00+08:00",
        "pop": 30.0,
        "wx_phenomenon": "多雲"
    }]
    
    saved_fc = store.save_forecasts(forecasts)
    assert saved_fc == 1
    
    # Save duplicate (should overwrite, returned inserted/updated count)
    saved_fc_dup = store.save_forecasts(forecasts)
    assert saved_fc_dup == 1
    
    fc_results = store.get_latest_forecasts()
    assert len(fc_results) == 1
    assert fc_results[0]["location_name"] == "高雄市"
    assert fc_results[0]["pop"] == 30.0
    
    # Save dummy observation
    obs = [{
        "station_id": "C0V890",
        "station_name": "旗津",
        "county": "高雄市",
        "town": "旗津區",
        "obs_time": "2026-07-09T22:00:00+08:00",
        "latitude": 22.6,
        "longitude": 120.27,
        "elevation": 5.0,
        "precipitation_now": 0.5,
        "precipitation_1hr": 1.2,
        "precipitation_24hr": 5.5
    }]
    
    saved_obs = store.save_observations(obs)
    assert saved_obs == 1
    
    obs_results = store.get_latest_observations()
    assert len(obs_results) == 1
    assert obs_results[0]["station_id"] == "C0V890"
    assert obs_results[0]["precipitation_24hr"] == 5.5
    
    # Save dummy QPF
    qpf_data = {
        "obs_time": "2026-07-09T22:10:00+08:00",
        "latitude": 22.62,
        "longitude": 120.28,
        "qpf_1hr_mm": 2.5
    }
    saved_qpf = store.save_qpf(qpf_data)
    assert saved_qpf == 1
    
    qpf_results = store.get_latest_qpf(latitude=22.62, longitude=120.28)
    assert len(qpf_results) == 1
    assert qpf_results[0]["qpf_1hr_mm"] == 2.5
    assert qpf_results[0]["obs_time"] == "2026-07-09T22:10:00+08:00"
    
    stats = store.get_db_stats()
    assert stats["forecast_total_rows"] == 1
    assert stats["observation_total_rows"] == 1
    assert stats["qpf_total_rows"] == 1


MOCK_QPF_JSON = {
    "cwaopendata": {
        "dataset": {
            "datasetInfo": {
                "parameterSet": {
                    "StartPointLongitude": "118.0",
                    "StartPointLatitude": "20.0",
                    "GridResolution": "0.0125",
                    "GridDimensionX": "4",
                    "GridDimensionY": "4",
                    "DateTime": "2026-07-09T22:10:00+08:00"
                }
            },
            "contents": {
                "content": "0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0,6.5,7.0,7.5"
            }
        }
    }
}

def test_client_get_qpf():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_QPF_JSON
    mock_resp.raise_for_status = lambda: None
    
    mock_instance = AsyncMock()
    mock_instance.get.return_value = mock_resp
    
    with patch("app.cwa_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        client = CWAClient("dummy_key")
        qpf = asyncio.run(client.get_qpf(lat=20.0125, lon=118.0125))
        assert qpf is not None
        assert qpf["qpf_1hr_mm"] == 2.5
        assert qpf["latitude"] == 20.0125
        assert qpf["longitude"] == 118.0125


