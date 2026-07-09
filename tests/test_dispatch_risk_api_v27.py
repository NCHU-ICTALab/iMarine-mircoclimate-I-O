from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_api_v27_target_area_contract(monkeypatch):
    def fake_response(
        target_area: str = "KHH",
        target_station_id: str | None = None,
        refresh_port_local: bool = False,
        no_realtime_khwd_mode: bool = False,
    ) -> dict:
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.7",
            "target_area": {"name": "Kaohsiung Port", "port_code": target_area, "target_mode": "port_area"},
            "station_priority_summary": {
                "prediction_mode": "fallback_baseline",
                "target_area": target_area,
                "fallback_to_467441": True,
                "467441_used_as_core_station": False,
            },
            "forecast_anchors": [
                {"label": "H1", "dispatch_risk_level": "normal", "dispatch_action_level": "normal_dispatch"}
            ],
            "trace": {
                "station_priority_policy": "port_local_first",
                "467441_used_as_core_station": False,
                "target_station_id_parameter_received": target_station_id,
            },
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_response)
    response = TestClient(api_module.app).get("/api/v1/dispatch/risk?target_area=KHH")

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "kaohsiung_port_dispatch_risk_v2.7"
    assert body["target_area"]["port_code"] == "KHH"
    assert body["station_priority_summary"]["prediction_mode"] == "fallback_baseline"
    assert body["trace"]["station_priority_policy"] == "port_local_first"
    assert body["trace"]["467441_used_as_core_station"] is False
    assert body["forecast_anchors"][0]["dispatch_action_level"] == "normal_dispatch"
