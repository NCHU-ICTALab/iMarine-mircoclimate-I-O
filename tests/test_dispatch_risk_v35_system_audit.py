from fastapi.testclient import TestClient

from app.api import app
from kaohsiung_microclimate_lstm.src import predict as predict_module
from kaohsiung_microclimate_lstm.src import preprocess as preprocess_module
from kaohsiung_microclimate_lstm.src import system_audit


def test_v35_system_audit_endpoint_exists():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")

    assert response.status_code == 200
    data = response.json()
    assert data["model_version"] == "kaohsiung_port_dispatch_risk_v1.3"
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


def test_system_audit_builds_payloads_through_current_prediction_entry(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(preprocess_module, "load_observations", lambda path: ["obs"])

    def fake_current(**kwargs):
        calls.append(kwargs["no_realtime_khwd_mode"])
        return {"model_version": "test", "mode": kwargs["no_realtime_khwd_mode"]}

    monkeypatch.setattr(predict_module, "predict_dispatch_risk_current", fake_current)

    normal, no_realtime = system_audit._load_or_build_prediction_payloads(
        tmp_path / "config.yaml",
        tmp_path,
        None,
        None,
    )

    assert calls == [False, True]
    assert normal["mode"] is False
    assert no_realtime["mode"] is True
