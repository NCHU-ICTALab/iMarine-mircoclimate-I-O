import json
from pathlib import Path

from kaohsiung_microclimate_lstm.src.system_audit import build_v35_system_audit


def test_v35_ui_dashboard_payload_has_required_sections():
    project = Path("kaohsiung_microclimate_lstm")
    build_v35_system_audit(
        config_path=project / "config.yaml",
        target_area="KHH",
        report_dir=project / "results" / "dispatch_risk_v35",
        project_root=project,
    )
    payload_path = project / "results" / "dispatch_risk_v35" / "ui_dashboard_payload_v35.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert "dashboard_cards" in payload
    assert "tables" in payload
    assert "data_sources" in payload["tables"]
    assert "stations" in payload["tables"]
    assert "dataset_durations" in payload["tables"]
    assert "model_metrics" in payload["tables"]
    assert "model_selection" in payload["tables"]
