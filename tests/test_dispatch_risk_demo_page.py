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


def test_dispatch_risk_demo_page_uses_meteorological_labels():
    response = TestClient(app).get("/dispatch-risk-demo")

    assert response.status_code == 200
    for forbidden in ["正常", "注意", "警戒", "一般風險", "停止暴露作業"]:
        assert forbidden not in response.text
    for rain_level in ['"無": "normal"', '"小雨": "watch"', '"大雨": "warning"', '"豪雨": "high_risk"', '"大豪雨": "stop"', '"超大豪雨": "stop"']:
        assert rain_level in response.text
    assert "觸發港區即時安全門檻" in response.text
