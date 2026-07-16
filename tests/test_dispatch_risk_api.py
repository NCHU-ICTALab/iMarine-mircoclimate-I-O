import json
import threading
import time

from fastapi.testclient import TestClient

from app import api as api_module


def test_dispatch_risk_endpoint_returns_v27_json(monkeypatch):
    called = {}

    def fake_dispatch_risk_response(target_area: str = "KHH", target_station_id: str | None = None, refresh_port_local: bool = False, no_realtime_khwd_mode: bool = False) -> dict:
        called["target_area"] = target_area
        called["target_station_id"] = target_station_id
        called["no_realtime_khwd_mode"] = no_realtime_khwd_mode
        return {
            "model_version": "kaohsiung_port_dispatch_risk_v2.7",
            "target_area": {"port_code": "KHH"},
            "station_priority_summary": {"prediction_mode": "fallback_baseline"},
            "forecast_anchors": [
                {
                    "label": "H2",
                    "dispatch_risk_level": "normal",
                    "risk_trigger_detail": {
                        "primary_trigger": "none",
                        "primary_trigger_level": "normal",
                        "primary_trigger_reliability": None,
                        "is_low_reliability_trigger": False,
                    },
                    "dispatch_action_level": "normal_dispatch",
                }
            ],
            "trace": {
                "cwa_pop_used_as_model_input": False,
                "normal_state_primary_trigger_none": True,
                "risk_trigger_semantics_patch_applied": True,
                "station_priority_policy": "port_local_first",
                "467441_used_as_core_station": False,
            },
        }

    monkeypatch.setattr(api_module, "build_dispatch_risk_response", fake_dispatch_risk_response)
    client = TestClient(api_module.app)

    response = client.get("/api/v1/dispatch/risk?target_station_id=467441")

    assert response.status_code == 200
    body = response.json()
    assert called["target_area"] == "KHH"
    assert called["target_station_id"] == "467441"
    assert body["model_version"] == "kaohsiung_port_dispatch_risk_v2.7"
    assert body["forecast_anchors"][0]["risk_trigger_detail"]["primary_trigger"] == "none"
    assert body["forecast_anchors"][0]["dispatch_action_level"] == "normal_dispatch"
    assert body["trace"]["cwa_pop_used_as_model_input"] is False


def test_build_dispatch_risk_response_caches_same_key_and_refresh_bypasses(monkeypatch, tmp_path):
    data = tmp_path / "data" / "raw" / "observed_hourly" / "467441.csv"
    config = tmp_path / "config.yaml"
    data.parent.mkdir(parents=True)
    data.write_text("obs_time,wind_speed\n2026-07-01,1\n", encoding="utf-8")
    config.write_text("project: {model_version: test}\n", encoding="utf-8")
    monkeypatch.setattr(api_module, "MICROCLIMATE_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(api_module, "MICROCLIMATE_CONFIG_PATH", config)
    monkeypatch.setattr(api_module, "_dispatch_risk_cache", {})

    calls = {"count": 0}

    def fake_compute(*args, **kwargs):
        calls["count"] += 1
        return {"model_version": "test", "call_count": calls["count"]}

    from kaohsiung_microclimate_lstm.src.tools import fetch_port_local_stations

    monkeypatch.setattr(fetch_port_local_stations, "run_fetch_port_local_stations", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(api_module, "_compute_dispatch_risk_response", fake_compute)

    first = api_module.build_dispatch_risk_response()
    second = api_module.build_dispatch_risk_response()
    refreshed = api_module.build_dispatch_risk_response(refresh_port_local=True)

    assert first == {"model_version": "test", "call_count": 1}
    assert second == {"model_version": "test", "call_count": 1}
    assert refreshed == {"model_version": "test", "call_count": 2}


def test_dispatch_risk_frontend_metrics_reads_h1_rain_classification_metrics(tmp_path):
    metrics_dir = tmp_path / "results" / "dispatch_risk_v32"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "nearby_cwa_model_metrics.json").write_text(
        json.dumps(
            {
                "rain_probability": {
                    "H1": {"CSI": 0.5524, "POD": 0.6259, "FAR": 0.1754},
                    "H2": {"CSI": 0.1111, "POD": 0.2222, "FAR": 0.3333},
                    "H3": {"CSI": 0.3185, "POD": 0.3597, "FAR": 0.2647},
                    "H4": {"CSI": 0.4444, "POD": 0.5555, "FAR": 0.6666},
                }
            }
        ),
        encoding="utf-8",
    )

    result = api_module._dispatch_risk_frontend_metrics(tmp_path)

    assert result["available"] is True
    assert result["horizon"] == "H1"
    assert result["target"] == "rain_probability"
    assert result["csi"] == 0.5524
    assert result["pod"] == 0.6259
    assert result["far"] == 0.1754
    assert result["metrics_report_generated_at"] is not None
    assert result["by_horizon"] == {
        "H1": {"csi": 0.5524, "pod": 0.6259, "far": 0.1754},
        "H2": {"csi": 0.1111, "pod": 0.2222, "far": 0.3333},
        "H3": {"csi": 0.3185, "pod": 0.3597, "far": 0.2647},
        "H4": {"csi": 0.4444, "pod": 0.5555, "far": 0.6666},
    }


def test_dispatch_risk_frontend_metrics_marks_unavailable_without_report(tmp_path):
    result = api_module._dispatch_risk_frontend_metrics(tmp_path)

    assert result["available"] is False
    assert result["csi"] is None
    assert result["pod"] is None
    assert result["far"] is None
    assert result["metrics_report_generated_at"] is None
    assert result["by_horizon"] == {
        "H1": {"csi": None, "pod": None, "far": None},
        "H2": {"csi": None, "pod": None, "far": None},
        "H3": {"csi": None, "pod": None, "far": None},
        "H4": {"csi": None, "pod": None, "far": None},
    }


def test_compute_dispatch_risk_response_adds_top_level_metrics(monkeypatch, tmp_path):
    metrics_dir = tmp_path / "results" / "dispatch_risk_v32"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "nearby_cwa_model_metrics.json").write_text(
        json.dumps({"rain_probability": {"H1": {"CSI": 0.5, "POD": 0.6, "FAR": 0.2}}}),
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data = tmp_path / "data.csv"

    from kaohsiung_microclimate_lstm.src import predict as predict_module
    from kaohsiung_microclimate_lstm.src import preprocess as preprocess_module

    monkeypatch.setattr(api_module, "MICROCLIMATE_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(preprocess_module, "load_observations", lambda path: ["obs"])
    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_current",
        lambda **kwargs: {"model_version": "test", "forecast_anchors": []},
    )

    result = api_module._compute_dispatch_risk_response(data, config, "KHH", None, None, False)

    assert result["metrics"] == {
        "available": True,
        "horizon": "H1",
        "target": "rain_probability",
        "source_model": "nearby_cwa_historical_model",
        "csi": 0.5,
        "pod": 0.6,
        "far": 0.2,
        "by_horizon": {
            "H1": {"csi": 0.5, "pod": 0.6, "far": 0.2},
            "H2": {"csi": None, "pod": None, "far": None},
            "H3": {"csi": None, "pod": None, "far": None},
            "H4": {"csi": None, "pod": None, "far": None},
        },
        "metrics_report_generated_at": result["metrics"]["metrics_report_generated_at"],
    }


def test_dispatch_risk_cache_key_tracks_khwd_file_mtime(tmp_path):
    data = tmp_path / "467441.csv"
    config = tmp_path / "config.yaml"
    khwd_dir = tmp_path / "observed_hourly"
    khwd = khwd_dir / "KHWD01.csv"
    khwd_dir.mkdir()
    data.write_text("obs_time,wind_speed\n2026-07-01,1\n", encoding="utf-8")
    config.write_text("project: {model_version: test}\n", encoding="utf-8")
    khwd.write_text("obs_time,wind_speed\n2026-07-01,1\n", encoding="utf-8")

    first = api_module._dispatch_risk_cache_key("KHH", None, False, data, config, khwd_dir)
    time.sleep(0.02)
    khwd.write_text("obs_time,wind_speed\n2026-07-01,2\n", encoding="utf-8")
    second = api_module._dispatch_risk_cache_key("KHH", None, False, data, config, khwd_dir)

    assert first != second


def test_dispatch_risk_cache_miss_singleflight_deduplicates_same_key(monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "_dispatch_risk_cache", {})
    monkeypatch.setattr(api_module, "_dispatch_risk_inflight", {})
    calls = {"count": 0}

    def slow_compute(*args, **kwargs):
        calls["count"] += 1
        time.sleep(0.05)
        return {"model_version": "test", "call_count": calls["count"]}

    monkeypatch.setattr(api_module, "_compute_dispatch_risk_response", slow_compute)
    cache_key = ("KHH", None, False, 1.0, 2.0)
    results = []

    def worker():
        results.append(
            api_module._compute_or_wait_dispatch_risk_response(
                cache_key,
                tmp_path / "data.csv",
                tmp_path / "config.yaml",
                "KHH",
                None,
                None,
                False,
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["count"] == 1
    assert results == [{"model_version": "test", "call_count": 1}, {"model_version": "test", "call_count": 1}]


def test_dispatch_risk_cache_ttl_covers_frontend_retry_window():
    assert api_module._DISPATCH_RISK_CACHE_TTL_SECONDS >= 60.0


def test_cwa_history_diagnostics_declares_hours_scope(monkeypatch):
    async def fake_historyapi(hours):
        return {"ok": True, "hours": hours}

    async def fake_marine_history():
        return {"ok": True}

    monkeypatch.setattr(api_module, "inspect_historyapi", fake_historyapi)
    monkeypatch.setattr(api_module, "inspect_marine_history", fake_marine_history)

    response = TestClient(api_module.app).get("/cwa/history/diagnostics?hours=6")

    assert response.status_code == 200
    body = response.json()
    assert body["hours"] == 6
    assert body["hours_applies_to"] == ["official_land"]
    assert body["official_land"]["hours"] == 6
    assert body["marine"]["hours_parameter_applied"] is False
