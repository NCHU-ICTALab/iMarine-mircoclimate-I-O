from fastapi.testclient import TestClient

from app.api import app


def test_v35_system_audit_endpoint_exists():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")

    assert response.status_code == 200
    data = response.json()
    assert data["model_version"] == "kaohsiung_port_dispatch_risk_v3.5"
    assert "data_source_summary" in data
    assert "station_summary" in data
    assert "dataset_duration_summary" in data
    assert "model_accuracy_summary" in data
    assert "dashboard_cards" in data


def test_v35_does_not_fabricate_missing_metrics():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    data = response.json()

    assert data["trace"]["no_fabricated_metrics"] is True
    assert data["trace"]["no_fabricated_dataset_duration"] is True


def test_v35_station_roles_are_preserved():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    trace = response.json()["trace"]

    assert trace["467441_used_as_core_station"] is False
    assert trace["nearby_cwa_used_as_port_local_core"] is False
    assert trace["cwa_pop_used_as_model_input"] is False
    assert trace["rain_probability_preserved"] is True
