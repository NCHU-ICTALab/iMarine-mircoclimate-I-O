from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_endpoint_returns_v27_json(monkeypatch):
    called = {}

    def fake_dispatch_risk_response(target_area: str = "KHH", target_station_id: str | None = None, refresh_port_local: bool = False, no_realtime_khwd_mode: bool = False) -> dict:
        called["target_area"] = target_area
        called["target_station_id"] = target_station_id
        called["no_realtime_khwd_mode"] = no_realtime_khwd_mode
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.7",
            "target_area": {"port_code": "KHH"},
            "station_priority_summary": {"prediction_mode": "fallback_baseline"},
            "forecast_anchors": [
                {
                    "label": "H2",
                    "dispatch_risk_level": "normal",
                    "risk_trigger_detail": {
                        "primary_trigger": "none",
                        "primary_trigger_level": "normal",
                        "primary_trigger_reliability": None,
                        "is_low_reliability_trigger": False,
                    },
                    "dispatch_action_level": "normal_dispatch",
                }
            ],
            "trace": {
                "cwa_pop_used_as_model_input": False,
                "normal_state_primary_trigger_none": True,
                "risk_trigger_semantics_patch_applied": True,
                "station_priority_policy": "port_local_first",
                "467441_used_as_core_station": False,
            },
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_dispatch_risk_response)
    client = TestClient(api_module.app)

    response = client.get("/api/v1/dispatch/risk?target_station_id=467441")

    assert response.status_code == 200
    body = response.json()
    assert called["target_area"] == "KHH"
    assert called["target_station_id"] == "467441"
    assert body["model_version"] == "kaohsiung_port_dispatch_risk_v2.7"
    assert body["forecast_anchors"][0]["risk_trigger_detail"]["primary_trigger"] == "none"
    assert body["forecast_anchors"][0]["dispatch_action_level"] == "normal_dispatch"
    assert body["trace"]["cwa_pop_used_as_model_input"] is False


def test_build_dispatch_risk_response_caches_same_key_and_refresh_bypasses(monkeypatch, tmp_path):
    data = tmp_path / "data" / "raw" / "observed_hourly" / "467441.csv"
    config = tmp_path / "config.yaml"
    data.parent.mkdir(parents=True)
    data.write_text("obs_time,wind_speed\n2026-07-01,1\n", encoding="utf-8")
    config.write_text("project: {model_version: test}\n", encoding="utf-8")
    monkeypatch.setattr(api_module, "MICROCLIMATE_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(api_module, "MICROCLIMATE_CONFIG_PATH", config)
    monkeypatch.setattr(api_module, "_dispatch_risk_cache", {})

    calls = {"count": 0}

    def fake_compute(*args, **kwargs):
        calls["count"] += 1
        return {"model_version": "test", "call_count": calls["count"]}

    from kaohsiung_microclimate_lstm.src.tools import fetch_port_local_stations

    monkeypatch.setattr(fetch_port_local_stations, "run_fetch_port_local_stations", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(api_module, "_compute_dispatch_risk_response", fake_compute)

    first = api_module.build_dispatch_risk_response()
    second = api_module.build_dispatch_risk_response()
    refreshed = api_module.build_dispatch_risk_response(refresh_port_local=True)

    assert first == {"model_version": "test", "call_count": 1}
    assert second == {"model_version": "test", "call_count": 1}
    assert refreshed == {"model_version": "test", "call_count": 2}
