from fastapi.testclient import TestClient

from app import api as api_module


def test_admin_fetch_microclimate_sources_uses_shared_runner(monkeypatch):
    called = {}

    def fake_runner(project_root, config_path):
        called["project_root"] = str(project_root)
        called["config_path"] = str(config_path)
        return {"success": True, "success_count": 4, "task_count": 4, "tasks": {}}

    monkeypatch.setattr(api_module, "run_microclimate_source_fetch", fake_runner)

    response = TestClient(api_module.app).post("/admin/fetch-microclimate-sources")

    assert response.status_code == 200
    assert response.json()["success_count"] == 4
    assert called["project_root"].endswith("kaohsiung_microclimate_lstm")
    assert called["config_path"].endswith("config.yaml")


def test_scheduler_status_endpoint_reports_disabled_by_default():
    response = TestClient(api_module.app).get("/admin/scheduler-status")

    assert response.status_code == 200
    body = response.json()
    assert body["configured_enabled"] is False
    assert body["enabled"] is False
    assert {job["id"] for job in body["jobs"]} >= {
        "port_local",
        "marine_realtime",
        "nearby_cwa_live",
        "cwa_forecast_history",
    }
