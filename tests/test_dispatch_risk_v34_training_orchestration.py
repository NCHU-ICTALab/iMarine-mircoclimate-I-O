import json

from kaohsiung_microclimate_lstm.src.training_orchestration import run_training_orchestration


def _config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v3.4, model_version: kaohsiung_port_dispatch_risk_v3.4}
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
training_orchestration: {report_dir: results/dispatch_risk_v34}
""",
        encoding="utf-8",
    )
    return cfg


def _accepted_manifest(tmp_path):
    artifact = tmp_path / "models" / "nearby_cwa_v34" / "wind_speed_model.joblib"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("model", encoding="utf-8")
    manifest = {
        "model_version": "kaohsiung_port_dispatch_risk_v3.4",
        "model_family": "nearby_cwa_historical_model",
        "model_artifact_version": "nearby_cwa_v34",
        "target_area": "KHH",
        "trained": True,
        "selected_station_ids": ["C0V890", "C0V490"],
        "all_selected_stations_closer_than_467441": True,
        "is_port_local_core": False,
        "models": {"wind_speed": {"artifact_path": str(artifact), "accepted": True}},
        "acceptance": {"model_accepted": True, "critical_under_warning_count": 0},
    }
    (artifact.parent / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_v34_skips_training_when_existing_accepted_model_manifest_exists(tmp_path):
    cfg = _config(tmp_path)
    _accepted_manifest(tmp_path)

    result = run_training_orchestration(config_path=cfg, project_root=tmp_path, target_area="KHH")

    assert result["training_checked"] is True
    assert result["training_required"] is False
    assert result["training_skipped"] is True
    assert result["models"]["nearby_cwa_historical_model"]["accepted"] is True


def test_v34_trains_when_no_accepted_model_manifest_exists(tmp_path):
    cfg = _config(tmp_path)

    result = run_training_orchestration(
        config_path=cfg,
        project_root=tmp_path,
        target_area="KHH",
        simulate_missing_manifest=True,
    )

    assert result["training_checked"] is True
    assert result["training_required"] is True
    assert result["training_skipped"] is False
