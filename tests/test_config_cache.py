from pathlib import Path

import yaml

from kaohsiung_microclimate_lstm.src import config as config_module


def test_load_config_uses_mtime_cache_and_returns_copy(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60]
targets: {wind_speed_gust: {variables: [wind_speed, wind_gust]}}
""".lstrip(),
        encoding="utf-8",
    )
    calls = {"count": 0}
    real_safe_load = yaml.safe_load

    def counted_safe_load(stream):
        calls["count"] += 1
        return real_safe_load(stream)

    monkeypatch.setattr(config_module.yaml, "safe_load", counted_safe_load)

    first = config_module.load_config(cfg_path)
    first["time_step_minutes"] = 999
    second = config_module.load_config(Path(cfg_path))

    assert calls["count"] == 1
    assert second["time_step_minutes"] == 10
