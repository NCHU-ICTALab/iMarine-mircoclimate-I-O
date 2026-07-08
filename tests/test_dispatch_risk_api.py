from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_endpoint_returns_v252_json(monkeypatch):
    called = {}

    def fake_dispatch_risk_response(target_station_id: str) -> dict:
        called["target_station_id"] = target_station_id
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.5.2",
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
            },
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_dispatch_risk_response)
    client = TestClient(api_module.app)

    response = client.get("/api/v1/dispatch/risk?target_station_id=467441")

    assert response.status_code == 200
    body = response.json()
    assert called["target_station_id"] == "467441"
    assert body["model_version"] == "kaohsiung_port_dispatch_risk_v2.5.2"
    assert body["forecast_anchors"][0]["risk_trigger_detail"]["primary_trigger"] == "none"
    assert body["forecast_anchors"][0]["dispatch_action_level"] == "normal_dispatch"
    assert body["trace"]["cwa_pop_used_as_model_input"] is False
