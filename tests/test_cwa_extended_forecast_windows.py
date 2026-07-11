from datetime import datetime
from zoneinfo import ZoneInfo

from kaohsiung_microclimate_lstm.src import predict as predict_module
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
    assert extended["windows"][0]["wind_speed"]["basis"] == "cwa_beaufort_scale_range_not_precise_value"
    assert extended["windows"][0]["rain_probability"]["level"] == "watch"
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
