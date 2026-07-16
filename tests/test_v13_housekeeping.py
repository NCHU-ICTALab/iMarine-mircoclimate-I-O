from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_readme_and_smoke_config_do_not_advertise_stale_dispatch_version():
    readme = (ROOT / "kaohsiung_microclimate_lstm" / "README.md").read_text(encoding="utf-8")
    smoke = yaml.safe_load((ROOT / "kaohsiung_microclimate_lstm" / "config_smoke.yaml").read_text(encoding="utf-8"))

    assert "kaohsiung_port_dispatch_risk_v3.5" not in readme
    assert "predict_dispatch_risk_v34" not in readme
    assert smoke["project"]["version"] == "v1.3"
    assert smoke["project"]["model_version"] == "kaohsiung_port_dispatch_risk_v1.3"
    assert "stale_model_policy" not in smoke.get("model_registry", {})


def test_primary_config_has_no_dead_stale_model_policy():
    config = yaml.safe_load((ROOT / "kaohsiung_microclimate_lstm" / "config.yaml").read_text(encoding="utf-8"))

    assert "stale_model_policy" not in config.get("model_registry", {})


def test_high_frequency_json_writers_use_atomic_write_json():
    files = [
        ROOT / "kaohsiung_microclimate_lstm" / "src" / "predict.py",
        ROOT / "kaohsiung_microclimate_lstm" / "src" / "cwa" / "pop3h_client.py",
        ROOT / "kaohsiung_microclimate_lstm" / "src" / "cwa" / "cwa_open_data_client.py",
        ROOT / "kaohsiung_microclimate_lstm" / "src" / "tools" / "fetch_port_local_stations.py",
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "atomic_write_json" in text
        assert ".write_text(json.dumps" not in text


def test_predict_module_has_no_dead_legacy_dispatch_version_strings():
    predict_source = (ROOT / "kaohsiung_microclimate_lstm" / "src" / "predict.py").read_text(encoding="utf-8")

    assert re.search(r"kaohsiung_port_dispatch_risk_v[23]\.", predict_source) is None
