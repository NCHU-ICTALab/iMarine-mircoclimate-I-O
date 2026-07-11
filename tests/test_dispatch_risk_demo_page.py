from fastapi.testclient import TestClient

from app.api import app


def test_dispatch_risk_demo_page_contains_frontend_contract():
    response = TestClient(app).get("/dispatch-risk-demo")

    assert response.status_code == 200
    assert "高雄港微氣候派工風險" in response.text
    assert "/api/v1/dispatch/risk" in response.text
    assert "抓取最新資料" in response.text
    assert "/admin/fetch-microclimate-sources" in response.text
    assert "station_priority_summary" in response.text
    assert "forecast_anchors" in response.text
    assert "CWA +3h/+6h" in response.text
    assert "extended_forecast_windows" in response.text
