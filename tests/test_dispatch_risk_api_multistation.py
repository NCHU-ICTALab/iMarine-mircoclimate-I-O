from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_api_returns_v27_station_priority_contract(monkeypatch):
    def fake_response(
        target_area: str = "KHH",
        target_station_id: str | None = None,
        refresh_port_local: bool = False,
        no_realtime_khwd_mode: bool = False,
    ) -> dict:
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.7",
            "target_area": {"port_code": target_area, "target_mode": "port_area"},
            "station_priority_summary": {
                "prediction_mode": "port_local_postprocess",
                "target_area": target_area,
                "using_port_local_station": True,
                "port_local_station_count": 2,
                "port_local_station_ids": ["KHWD01", "KHWD04"],
                "fallback_to_467441": False,
                "fallback_reason": None,
                "station_priority_policy": "port_local_first",
            },
            "forecast_anchors": [{"label": "H1", "dispatch_risk_level": "normal", "dispatch_action_level": "normal_dispatch"}],
            "trace": {"station_priority_policy": "port_local_first", "467441_used_as_core_station": False},
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_response)
    client = TestClient(api_module.app)

    response = client.get("/api/v1/dispatch/risk?target_station_id=467441")

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "kaohsiung_port_dispatch_risk_v2.7"
    assert body["station_priority_summary"]["using_port_local_station"] is True
    assert body["trace"]["467441_used_as_core_station"] is False
    assert body["forecast_anchors"][0]["dispatch_action_level"] == "normal_dispatch"
