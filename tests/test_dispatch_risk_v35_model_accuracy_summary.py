from fastapi.testclient import TestClient

from app.api import app


def test_v35_model_accuracy_summary_uses_error_metrics_not_accuracy_for_regression():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    model_summary = response.json()["model_accuracy_summary"]

    nearby = model_summary["nearby_cwa_historical_model"]
    assert nearby["trained"] is True
    assert nearby["accepted"] is True
    assert nearby["wind_speed_h1_mae_mps"] is not None
    assert nearby["wind_gust_h1_mae_mps"] is not None
    assert nearby["rain_probability_brier_score"] is not None


def test_v35_port_local_model_is_not_activated():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    port = response.json()["model_accuracy_summary"]["port_local_model"]

    assert port["trained"] is False
    assert port["accepted"] is False
