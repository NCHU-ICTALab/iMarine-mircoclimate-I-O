import json

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations import append_station_frame, run_fetch_port_local_stations


class FakeClient:
    def __init__(self, available):
        self.available = available

    def fetch_station_latest(self, station_id):
        if station_id not in self.available:
            return {"station_id": station_id, "available": False, "raw_records": [], "error": "No records returned."}
        return {
            "station_id": station_id,
            "available": True,
            "raw_records": [
                {
                    "obs_time": "2026-07-08T10:00:00+08:00",
                    "WS_AVG": 11.0,
                    "WS_MAX": 14.0,
                    "WD_AVG": 180.0,
                }
            ],
            "error": None,
        }


def _write_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
time_step_minutes: 10
lookback_hours: 12
horizon_minutes: 120
anchor_offsets_minutes: [30, 60, 90, 120]
project: {version: v2.8, model_version: kaohsiung_port_dispatch_risk_v2.8}
targets:
  precipitation: {variables: [precipitation_1hr], model_type: twostage_lstm}
  wind_speed_gust: {variables: [wind_speed, wind_gust], model_type: multitask_lstm}
station_pool:
  station_pool_config: config/station_pool.yaml
  min_required_port_local_wind_stations: 2
port_local_data_acquisition:
  enabled: true
  output_dir: data/raw/observed_hourly
  report_dir: results/port_local_data_v28
""",
        encoding="utf-8",
    )
    pool_dir = tmp_path / "config"
    pool_dir.mkdir()
    (pool_dir / "station_pool.yaml").write_text(
        """
station_pool_version: v2.7
station_pool_mode: port_local_priority
priority_groups:
  port_local_wind:
    priority: 1
    required_for_core_prediction: true
    stations:
      - {station_id: KHWD01, type: wind, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
      - {station_id: KHWD04, type: wind, role: port_local_wind_station, is_port_local: true, is_core_station: true, enabled: true}
  fallback_baseline:
    priority: 5
    stations:
      - {station_id: "467441", type: weather, role: fallback_baseline, is_port_local: false, is_core_station: false, usage: fallback_only, enabled: true}
""",
        encoding="utf-8",
    )
    return cfg


def test_fetch_tool_writes_reports_and_recommends_postprocess(tmp_path):
    cfg = _write_config(tmp_path)

    result = run_fetch_port_local_stations(config_path=cfg, project_root=tmp_path, client=FakeClient({"KHWD01", "KHWD04"}))

    assert (tmp_path / "data" / "raw" / "observed_hourly" / "KHWD01.csv").exists()
    assert (tmp_path / "results" / "port_local_data_v28" / "fetch_report.json").exists()
    availability = json.loads((tmp_path / "results" / "port_local_data_v28" / "station_availability_report.json").read_text(encoding="utf-8"))
    assert availability["recommended_prediction_mode"] == "port_local_postprocess"
    assert result["port_local_data_refresh_success"] is True


def test_fetch_tool_recommends_fallback_when_khwd_missing(tmp_path):
    cfg = _write_config(tmp_path)

    result = run_fetch_port_local_stations(config_path=cfg, project_root=tmp_path, client=FakeClient(set()))

    availability = result["station_availability_report"]
    assert availability["recommended_prediction_mode"] == "fallback_baseline"
    assert availability["fallback_to_467441_required"] is True


def test_append_station_frame_preserves_existing_rows_and_deduplicates(tmp_path):
    csv_path = tmp_path / "KHWD01.csv"
    pd.DataFrame(
        [
            {"station_id": "KHWD01", "obs_time": "2026-07-08T10:00:00+08:00", "wind_speed": 1.0},
            {"station_id": "KHWD01", "obs_time": "2026-07-08T10:10:00+08:00", "wind_speed": 2.0},
        ]
    ).to_csv(csv_path, index=False)

    combined = append_station_frame(
        csv_path,
        pd.DataFrame(
            [
                {"station_id": "KHWD01", "obs_time": "2026-07-08T10:10:00+08:00", "wind_speed": 3.0},
                {"station_id": "KHWD01", "obs_time": "2026-07-08T10:20:00+08:00", "wind_speed": 4.0},
            ]
        ),
    )

    assert len(combined) == 3
    saved = pd.read_csv(csv_path)
    assert saved["obs_time"].tolist() == [
        "2026-07-08T10:00:00+08:00",
        "2026-07-08T10:10:00+08:00",
        "2026-07-08T10:20:00+08:00",
    ]
    assert saved.loc[saved["obs_time"] == "2026-07-08T10:10:00+08:00", "wind_speed"].iloc[0] == 3.0
