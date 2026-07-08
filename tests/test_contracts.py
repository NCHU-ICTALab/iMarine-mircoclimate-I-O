from datetime import datetime

from app.contracts import SCHEMA_VERSION, current_response, observation_record, schema_response
from app.models import TAIPEI, TwPortObservation


def sample_observation() -> TwPortObservation:
    return TwPortObservation(
        source="twport",
        port_code="5",
        station_id="KHWD01M01",
        station_name="高雄港第一港口風力觀測站",
        location="10號碼頭",
        device_type="WIND",
        obs_time=datetime(2026, 7, 2, 18, 40, tzinfo=TAIPEI),
        longitude=120.28,
        latitude=22.61,
        wind_speed=2.5,
        wind_gust=4.1,
        wind_direction=270.0,
        confidence="high",
        stale=False,
        fetched_at=datetime(2026, 7, 2, 18, 43, tzinfo=TAIPEI),
    )


def test_observation_record_has_stable_v1_shape():
    record = observation_record(
        sample_observation(),
        generated_at=datetime(2026, 7, 2, 18, 45, tzinfo=TAIPEI),
        include_runtime_status=True,
    )

    assert set(record) == {"record_id", "source", "device_type", "station", "time", "metrics", "quality"}
    assert record["station"]["station_id"] == "KHWD01M01"
    assert record["time"]["time_zone"] == "Asia/Taipei"
    assert "wind_speed_mps" in record["metrics"]
    assert "precipitation_1hr_mm" in record["metrics"]
    assert "status_level" in record["quality"]
    assert "raw_data" not in record


def test_current_response_uses_schema_version_and_flat_data():
    response = current_response([sample_observation()])

    assert response["schema_version"] == SCHEMA_VERSION
    assert response["endpoint"] == "/api/v1/microclimate/current"
    assert response["data_quality"]["record_count"] == 1
    assert isinstance(response["data"], list)
    assert response["data"][0]["metrics"]["wind_gust_mps"] == 4.1


def test_schema_response_documents_stable_endpoints():
    response = schema_response()

    assert response["schema_version"] == SCHEMA_VERSION
    assert "/api/v1/microclimate/current" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/dispatch/risk" in response["metadata"]["stable_endpoints"]
    assert "observation_record" in response["metadata"]
