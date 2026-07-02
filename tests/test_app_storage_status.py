from datetime import datetime, timedelta

from app.models import TAIPEI, TwPortObservation
from app.storage import ObservationStore


def test_data_status_marks_latest_station_data_stale_against_current_time(tmp_path):
    store = ObservationStore(tmp_path / "test.sqlite3")
    now = datetime.now(TAIPEI)
    fresh = TwPortObservation(
        source="twport",
        port_code="5",
        station_id="WIND-1",
        station_name="Wind Station",
        location="Pier 1",
        device_type="WIND",
        obs_time=now - timedelta(minutes=5),
        wind_speed=3.2,
        fetched_at=now - timedelta(minutes=4),
    )
    old = TwPortObservation(
        source="cwa",
        port_code=None,
        station_id="CWA-1",
        station_name="Weather Station",
        location="Kaohsiung",
        device_type="WEATHER",
        obs_time=now - timedelta(minutes=45),
        air_temperature=30.0,
        fetched_at=now - timedelta(minutes=44),
    )

    store.upsert_many([fresh, old])

    status = store.data_status(stale_after_minutes=20)

    assert status["overall"]["total_rows"] == 2
    assert status["overall"]["latest_station_count"] == 2
    assert status["overall"]["current_stale_count"] == 1
    assert status["overall"]["is_current"] is False

    station_status = {
        item["station_id"]: item["is_stale_now"]
        for item in status["stations"]
    }
    assert station_status == {"WIND-1": False, "CWA-1": True}


def test_data_status_uses_device_specific_thresholds_by_default(tmp_path):
    store = ObservationStore(tmp_path / "test.sqlite3")
    now = datetime.now(TAIPEI)
    cwa_hourly = TwPortObservation(
        source="cwa",
        port_code=None,
        station_id="CWA-1",
        station_name="Weather Station",
        location="Kaohsiung",
        device_type="WEATHER",
        obs_time=now - timedelta(minutes=45),
        air_temperature=30.0,
        fetched_at=now,
    )
    stale_wind = TwPortObservation(
        source="twport",
        port_code="5",
        station_id="WIND-1",
        station_name="Wind Station",
        location="Pier 1",
        device_type="WIND",
        obs_time=now - timedelta(minutes=45),
        wind_speed=3.2,
        fetched_at=now,
    )
    outage_wind = TwPortObservation(
        source="twport",
        port_code="5",
        station_id="WIND-OLD",
        station_name="Stopped Wind Station",
        location="Pier 2",
        device_type="WIND",
        obs_time=now - timedelta(days=2),
        wind_speed=3.2,
        fetched_at=now,
    )

    store.upsert_many([cwa_hourly, stale_wind, outage_wind])

    status = store.data_status()
    by_station = {item["station_id"]: item for item in status["stations"]}

    assert by_station["CWA-1"]["threshold_minutes"] == 75
    assert by_station["CWA-1"]["is_stale_now"] is False
    assert by_station["WIND-1"]["threshold_minutes"] == 20
    assert by_station["WIND-1"]["status_level"] == "stale"
    assert by_station["WIND-OLD"]["status_level"] == "outage"
