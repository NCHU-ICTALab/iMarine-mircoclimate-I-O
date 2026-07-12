import json
from datetime import datetime, timedelta

from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_refresh_cwa_forecast_source_uses_fresh_cache(monkeypatch, tmp_path):
    resolved_path = tmp_path / "config" / "resolved_cwa_forecast_source.json"
    resolved_path.parent.mkdir()
    resolved_path.write_text(
        json.dumps(
            {
                "available": True,
                "dataset_id": "cached",
                "resolved_at": datetime.now(predict_module.TAIPEI).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )
    called = {"count": 0}

    def fake_resolve(*args, **kwargs):
        called["count"] += 1
        return {"available": True, "dataset_id": "fresh", "resolved_at": datetime.now(predict_module.TAIPEI).isoformat(timespec="seconds")}

    monkeypatch.setattr(predict_module, "resolve_cwa_forecast_source", fake_resolve)

    result = predict_module.refresh_cwa_forecast_source_if_stale(
        {"cwa_open_data": {"enabled": True, "resolved_source_max_age_hours": 3}},
        tmp_path,
    )

    assert result["dataset_id"] == "cached"
    assert result["cache_status"] == "hit"
    assert called["count"] == 0


def test_refresh_cwa_forecast_source_refreshes_stale_cache(monkeypatch, tmp_path):
    resolved_path = tmp_path / "config" / "resolved_cwa_forecast_source.json"
    resolved_path.parent.mkdir()
    resolved_path.write_text(
        json.dumps(
            {
                "available": True,
                "dataset_id": "stale",
                "resolved_at": (datetime.now(predict_module.TAIPEI) - timedelta(hours=4)).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )

    def fake_resolve(*args, **kwargs):
        return {"available": True, "dataset_id": "fresh", "resolved_at": datetime.now(predict_module.TAIPEI).isoformat(timespec="seconds")}

    monkeypatch.setattr(predict_module, "resolve_cwa_forecast_source", fake_resolve)

    result = predict_module.refresh_cwa_forecast_source_if_stale(
        {"cwa_open_data": {"enabled": True, "resolved_source_max_age_hours": 3}},
        tmp_path,
    )

    saved = json.loads(resolved_path.read_text(encoding="utf-8"))
    assert result["dataset_id"] == "fresh"
    assert result["cache_status"] == "refreshed"
    assert saved["dataset_id"] == "fresh"
