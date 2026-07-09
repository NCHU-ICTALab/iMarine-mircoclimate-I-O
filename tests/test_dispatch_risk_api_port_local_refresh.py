from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_api_accepts_refresh_port_local(monkeypatch):
    called = {}

    def fake_response(
        target_area: str = "KHH",
        target_station_id: str | None = None,
        refresh_port_local: bool = False,
        no_realtime_khwd_mode: bool = False,
    ):
        called["refresh_port_local"] = refresh_port_local
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.8",
            "target_area": {"port_code": target_area},
            "station_priority_summary": {"prediction_mode": "fallback_baseline"},
            "forecast_anchors": [{"label": "H1", "dispatch_risk_level": "normal", "dispatch_action_level": "normal_dispatch"}],
            "trace": {
                "station_priority_policy": "port_local_first",
                "467441_used_as_core_station": False,
                "port_local_data_refresh_attempted": refresh_port_local,
            },
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_response)

    response = TestClient(api_module.app).get("/api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true")

    assert response.status_code == 200
    assert called["refresh_port_local"] is True
    assert response.json()["trace"]["port_local_data_refresh_attempted"] is True
