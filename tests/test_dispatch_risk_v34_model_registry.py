import json

from kaohsiung_microclimate_lstm.src.model_registry import build_model_registry, build_model_registry_summary, validate_model_manifest


def test_v34_model_manifest_validation_requires_artifacts(tmp_path):
    manifest_path = tmp_path / "models" / "nearby_cwa_v34" / "model_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "trained": True,
                "models": {"wind_speed": {"artifact_path": str(tmp_path / "missing.joblib")}},
                "acceptance": {"model_accepted": True, "critical_under_warning_count": 0},
            }
        ),
        encoding="utf-8",
    )

    result = validate_model_manifest(manifest_path, tmp_path)

    assert result["valid"] is False
    assert result["reason"] == "model_artifact_missing"


def test_v34_model_manifest_validation_checks_nested_horizon_artifacts(tmp_path):
    model_dir = tmp_path / "models" / "nearby_cwa_v34"
    model_dir.mkdir(parents=True)
    h1 = model_dir / "precipitation_amount_H1.joblib"
    h1.write_text("placeholder", encoding="utf-8")
    manifest_path = model_dir / "model_manifest.json"
    missing_h2 = "models/nearby_cwa_v34/precipitation_amount_H2.joblib"
    manifest_path.write_text(
        json.dumps(
            {
                "trained": True,
                "models": {
                    "precipitation_amount": {
                        "accepted": True,
                        "artifacts": {
                            "precipitation_amount_H1": {"artifact_path": "models/nearby_cwa_v34/precipitation_amount_H1.joblib"},
                            "precipitation_amount_H2": {"artifact_path": missing_h2},
                        },
                    }
                },
                "acceptance": {"model_accepted": True, "critical_under_warning_count": 0},
            }
        ),
        encoding="utf-8",
    )

    result = validate_model_manifest(manifest_path, tmp_path)

    assert result["valid"] is False
    assert result["reason"] == "model_artifact_missing"
    assert result["missing_artifacts"] == [missing_h2]


def test_v34_model_registry_summary_lists_available_models():
    summary = build_model_registry_summary(
        {
            "registry_version": "v3.4",
            "models": {
                "nearby_cwa_historical_model": {"available": True, "accepted": True},
                "port_local_model": {"available": False, "accepted": False},
            },
        }
    )

    assert summary["model_registry_used"] is True
    assert summary["available_model_families"] == ["nearby_cwa_historical_model"]
    assert summary["accepted_model_families"] == ["nearby_cwa_historical_model"]


def test_model_registry_includes_legacy_lstm_when_checkpoint_exists(tmp_path):
    checkpoint = tmp_path / "models" / "checkpoints" / "467441_wind_speed_gust_best.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("placeholder", encoding="utf-8")
    registry = build_model_registry(
        tmp_path,
        {"project": {"model_version": "test"}, "wind_speed_gust_prediction_source": "legacy_lstm"},
        {"valid": True, "trained": True, "accepted": True, "manifest": {"model_artifact_version": "nearby_cwa_v34"}, "manifest_path": str(tmp_path / "manifest.json")},
        "KHH",
    )

    legacy = registry["models"]["legacy_lstm"]
    assert legacy["available"] is True
    assert legacy["accepted"] is True
    assert legacy["default_for"] == ["wind_speed_gust"]
