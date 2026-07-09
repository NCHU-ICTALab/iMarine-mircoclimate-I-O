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
