import json

from kaohsiung_microclimate_lstm.src.model_registry import build_model_registry_summary, validate_model_manifest


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
