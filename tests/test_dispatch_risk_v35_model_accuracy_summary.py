from fastapi.testclient import TestClient

from app.api import app
from kaohsiung_microclimate_lstm.src.system_audit import _build_model_accuracy_summary


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


def test_v35_model_accuracy_summary_includes_legacy_lstm_actual_default():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    legacy = response.json()["model_accuracy_summary"]["legacy_lstm"]

    assert legacy["trained"] is True
    assert legacy["accepted"] is True
    assert legacy["activation_status"] == "default_base_wind_gust_source"
    assert legacy["metrics_available"] is False


def test_v35_model_accuracy_summary_marks_nearby_model_unavailable_when_artifacts_missing(tmp_path):
    manifest = tmp_path / "models" / "nearby_cwa_v34" / "model_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "trained": true,
  "selected_station_ids": ["C0V890"],
  "models": {
    "wind_speed": {
      "artifacts": {
        "wind_speed_H1": {"artifact_path": "models/nearby_cwa_v34/missing_H1.joblib"}
      }
    }
  },
  "acceptance": {"model_accepted": true, "critical_under_warning_count": 0}
}
""",
        encoding="utf-8",
    )

    summary = _build_model_accuracy_summary("test", "KHH", tmp_path)
    nearby = next(item for item in summary["models"] if item["model_id"] == "nearby_cwa_historical_model")

    assert nearby["trained"] is True
    assert nearby["accepted"] is True
    assert nearby["available"] is False
    assert nearby["reason"] == "model_artifact_missing"
    assert nearby["manifest_validation"]["missing_artifacts"] == ["models/nearby_cwa_v34/missing_H1.joblib"]
