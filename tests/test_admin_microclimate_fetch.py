from fastapi.testclient import TestClient

from app import api as api_module
from app import fetch_microclimate


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


def test_run_microclimate_source_fetch_force_refreshes_extended_cwa_forecast(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
rain_postprocess: {cwa_pop3h: {fallback_location: "前鎮區", cache_minutes: 30}}
extended_forecast_windows: {location_name: "前鎮區", cache_minutes: 30, data_id: F-D0047-065}
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(fetch_microclimate, "_fetch_port_local", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_fetch_marine_realtime", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_fetch_nearby_cwa_live", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_refresh_cwa_forecast_source", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_fetch_cwa_forecast_history", lambda *args, **kwargs: {"ok": True})

    from kaohsiung_microclimate_lstm.src.cwa import pop3h_client

    calls = {}

    def fake_fetch_pop3h(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {"available": True}

    monkeypatch.setattr(pop3h_client, "fetch_pop3h", fake_fetch_pop3h)

    result = fetch_microclimate.run_microclimate_source_fetch(tmp_path, cfg)

    assert result["success"] is True
    assert "cwa_extended_forecast" in result["tasks"]
    assert result["tasks"]["cwa_extended_forecast"]["success"] is True
    assert calls["args"][0] == "前鎮區"
    assert calls["kwargs"]["force_refresh"] is True
    assert calls["kwargs"]["include_wind_speed"] is True
    assert calls["kwargs"]["data_id"] == "F-D0047-065"


def test_run_microclimate_source_fetch_marks_nearby_cwa_all_station_failure(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("rain_postprocess: {cwa_pop3h: {fallback_location: 前鎮區}}\n", encoding="utf-8")
    monkeypatch.setattr(fetch_microclimate, "_fetch_port_local", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_fetch_marine_realtime", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        fetch_microclimate,
        "_fetch_nearby_cwa_live",
        lambda *args, **kwargs: {"rows_fetched": 0, "all_stations_failed": True},
    )
    monkeypatch.setattr(fetch_microclimate, "_refresh_cwa_forecast_source", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(fetch_microclimate, "_fetch_cwa_forecast_history", lambda *args, **kwargs: {"ok": True})

    from kaohsiung_microclimate_lstm.src.cwa import pop3h_client

    monkeypatch.setattr(pop3h_client, "fetch_pop3h", lambda *args, **kwargs: {"available": True})

    result = fetch_microclimate.run_microclimate_source_fetch(tmp_path, cfg)

    assert result["success"] is False
    assert result["tasks"]["nearby_cwa_live"]["success"] is False
    assert result["tasks"]["nearby_cwa_live"]["error"] == "all nearby CWA stations failed to fetch"
