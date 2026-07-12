import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from kaohsiung_microclimate_lstm.src import predict as predict_module
from kaohsiung_microclimate_lstm.src.cwa import pop3h_client
from kaohsiung_microclimate_lstm.src.cwa.pop3h_client import DATAID, _current_next, _parse_records, parse_beaufort_scale_min


def _realistic_body():
    return {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "LocationName": "前鎮區",
                            "WeatherElement": [
                                {
                                    "ElementName": "3小時降雨機率",
                                    "Time": [
                                        {
                                            "StartTime": "2026-07-11T18:00:00+08:00",
                                            "EndTime": "2026-07-11T21:00:00+08:00",
                                            "ElementValue": [{"ProbabilityOfPrecipitation": "40"}],
                                        },
                                        {
                                            "StartTime": "2026-07-11T21:00:00+08:00",
                                            "EndTime": "2026-07-12T00:00:00+08:00",
                                            "ElementValue": [{"ProbabilityOfPrecipitation": "70"}],
                                        },
                                    ],
                                },
                                {
                                    "ElementName": "風速",
                                    "Time": [
                                        {
                                            "StartTime": "2026-07-11T18:00:00+08:00",
                                            "EndTime": "2026-07-11T21:00:00+08:00",
                                            "ElementValue": [{"WindSpeed": ">= 11", "BeaufortScale": ">= 6"}],
                                        },
                                        {
                                            "StartTime": "2026-07-11T21:00:00+08:00",
                                            "EndTime": "2026-07-12T00:00:00+08:00",
                                            "ElementValue": [{"WindSpeed": "4-5", "BeaufortScale": "3-4"}],
                                        },
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    }


def test_parse_beaufort_scale_min_handles_cwa_range_formats():
    assert parse_beaufort_scale_min(">= 6") == 6
    assert parse_beaufort_scale_min("3-4") == 3
    assert parse_beaufort_scale_min("5級") == 5


def test_cwa_pop3h_parser_merges_rain_probability_and_beaufort_wind():
    records = _parse_records(_realistic_body(), "前鎮區")
    now = datetime(2026, 7, 11, 15, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    result = _current_next({"available": True, "data_id": DATAID, "location_name": "前鎮區", "records": records}, now)

    assert result["available"] is True
    assert result["current"] == 0.4
    assert result["next"] == 0.7
    assert result["current_wind_speed_mps"] is None
    assert result["current_wind"]["beaufort_scale_min"] == 6
    assert result["current_wind"]["beaufort_scale_text"] == ">= 6"
    assert result["current_wind"]["wind_speed_text"] == ">= 11"
    assert result["next_wind"]["beaufort_scale_min"] == 3


def test_current_next_rain_probability_uses_plus_3h_and_plus_6h_target_times():
    records = [
        {"start_time": "2026-07-12T18:00:00+08:00", "end_time": "2026-07-12T21:00:00+08:00", "pop": 0.3, "beaufort_scale_min": None},
        {"start_time": "2026-07-12T21:00:00+08:00", "end_time": "2026-07-13T00:00:00+08:00", "pop": 0.5, "beaufort_scale_min": None},
        {"start_time": "2026-07-12T22:00:00+08:00", "end_time": "2026-07-12T23:00:00+08:00", "pop": None, "beaufort_scale_min": 6, "wind_speed_text": ">= 11", "beaufort_scale_text": ">= 6"},
        {"start_time": "2026-07-13T00:00:00+08:00", "end_time": "2026-07-13T03:00:00+08:00", "pop": 0.2, "beaufort_scale_min": None},
        {"start_time": "2026-07-13T01:00:00+08:00", "end_time": "2026-07-13T02:00:00+08:00", "pop": None, "beaufort_scale_min": 3, "wind_speed_text": "4-5", "beaufort_scale_text": "3-4"},
    ]
    now = datetime(2026, 7, 12, 19, 38, tzinfo=ZoneInfo("Asia/Taipei"))

    result = _current_next({"available": True, "data_id": DATAID, "location_name": "前鎮區", "records": records}, now)

    assert result["current"] == 0.5
    assert result["next"] == 0.2
    assert result["current"] != result["next"]


def test_fetch_pop3h_force_refresh_bypasses_valid_cache(monkeypatch, tmp_path):
    cache = tmp_path / "data" / "cache" / f"cwa_pop3h_前鎮區_{DATAID}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "_cached_at": time.time(),
                "payload": {
                    "available": True,
                    "data_id": DATAID,
                    "location_name": "前鎮區",
                    "records": [
                        {"start_time": "2026-07-12T18:00:00+08:00", "end_time": "2026-07-13T03:00:00+08:00", "pop": 0.1}
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pop3h_client, "load_api_key", lambda: "KEY")
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return _realistic_body()

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr(pop3h_client.requests, "get", fake_get)

    cached = pop3h_client.fetch_pop3h("前鎮區", now=datetime(2026, 7, 11, 15, 30, tzinfo=ZoneInfo("Asia/Taipei")), project_root=tmp_path)
    refreshed = pop3h_client.fetch_pop3h("前鎮區", now=datetime(2026, 7, 11, 15, 30, tzinfo=ZoneInfo("Asia/Taipei")), project_root=tmp_path, force_refresh=True)

    assert cached["current"] == 0.1
    assert refreshed["current"] == 0.4
    assert calls["count"] == 1


def test_v35_attaches_extended_cwa_windows_and_frontend_cwa(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
project: {version: v3.5, model_version: kaohsiung_port_dispatch_risk_v3.5}
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
rain_postprocess: {cwa_pop3h: {fallback_location: 前鎮區, cache_minutes: 30}}
dispatch_thresholds:
  rain_probability: {watch: 0.30, warning: 0.50, high_risk: 0.70}
  wind_speed_mps: {watch: 8.0, warning: 10.8, high_risk: 13.9, stop: 17.2}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v34",
        lambda **kwargs: {
            "model_version": "kaohsiung_port_dispatch_risk_v3.4",
            "generated_at": "2026-07-11T19:00:00+08:00",
            "forecast_anchors": [{"label": "H1"}],
            "trace": {},
        },
    )

    def fake_fetch_pop3h(*args, **kwargs):
        assert kwargs["include_wind_speed"] is True
        assert kwargs["data_id"] == DATAID
        return {
            "available": True,
            "data_id": DATAID,
            "location_name": "前鎮區",
            "current": 0.4,
            "next": 0.7,
            "current_wind": {"wind_speed_text": ">= 11", "beaufort_scale_min": 6, "beaufort_scale_text": ">= 6"},
            "next_wind": {"wind_speed_text": "4-5", "beaufort_scale_min": 3, "beaufort_scale_text": "3-4"},
            "fetched_at": "2026-07-11T18:00:00+08:00",
        }

    monkeypatch.setattr(predict_module, "fetch_pop3h", fake_fetch_pop3h)

    result = predict_module.predict_dispatch_risk_v35(config_path=str(cfg), project_root=tmp_path)
    extended = result["extended_forecast_windows"]

    assert extended["available"] is True
    assert extended["source"] == "cwa_official_forecast"
    assert extended["data_id"] == DATAID
    assert [item["window"] for item in extended["windows"]] == ["+3h", "+6h"]
    assert extended["windows"][0]["wind_speed"]["value_mps"] is None
    assert extended["windows"][0]["wind_speed"]["beaufort_scale_min"] == 6
    assert extended["windows"][0]["wind_speed"]["operation_level"] == "warning"
    assert extended["windows"][0]["wind_speed"]["basis"] == "cwa_beaufort_scale_range_not_precise_value"
    assert extended["windows"][0]["rain_probability"]["level"] == "watch"
    assert extended["windows"][1]["wind_speed"]["operation_level"] == "normal"
    assert extended["windows"][0]["wind_gust"]["available"] is False
    assert extended["windows"][0]["visibility"]["available"] is False
    assert result["cwa"][0]["window"] == "+3h"
    assert result["cwa"][0]["rainLevel"] == "小雨"
    assert result["cwa"][0]["beaufort"] == 6
    assert result["trace"]["extended_cwa_forecast_windows_attached"] is True


def test_v35_extended_cwa_windows_degrade_without_breaking_h1_h4(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
project: {version: v3.5, model_version: kaohsiung_port_dispatch_risk_v3.5}
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
targets: {precipitation: {variables: [precipitation_1hr]}, wind_speed_gust: {variables: [wind_speed, wind_gust]}}
rain_postprocess: {cwa_pop3h: {fallback_location: 前鎮區}}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        predict_module,
        "predict_dispatch_risk_v34",
        lambda **kwargs: {
            "model_version": "kaohsiung_port_dispatch_risk_v3.4",
            "generated_at": "2026-07-11T19:00:00+08:00",
            "forecast_anchors": [{"label": "H1", "rain": {"final_probability": 0.2}}],
            "trace": {},
        },
    )
    monkeypatch.setattr(predict_module, "fetch_pop3h", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("quota exceeded")))

    result = predict_module.predict_dispatch_risk_v35(config_path=str(cfg), project_root=tmp_path)

    assert result["extended_forecast_windows"]["available"] is False
    assert result["extended_forecast_windows"]["source"] == "cwa_official_forecast"
    assert result["cwa"] == []
    assert result["forecast_anchors"][0]["label"] == "H1"
