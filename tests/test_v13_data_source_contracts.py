from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from kaohsiung_microclimate_lstm.src.data.fetch_marine_history import (
    DEFAULT_STATION_IDS,
    MARINE_COLUMNS,
    marine_payload_to_frame,
)
from kaohsiung_microclimate_lstm.src.data.fetch_qpesums import DATAID_QPE, DATAID_STATION_RAINFALL_QPE, fetch_qpe_current
from kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations import append_station_frame


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_v13_station_pool_contains_khwd_metadata_and_marks_khwd08_unavailable_not_pursued():
    pool = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config" / "station_pool.yaml").read_text(encoding="utf-8"))
    stations = {
        station["station_id"]: station
        for station in pool["priority_groups"]["port_local_wind"]["stations"]
    }

    for station_id in ["KHWD01", "KHWD04", "KHWD05", "KHWD06", "KHWD07"]:
        station = stations[station_id]
        assert station["lat"] is not None
        assert station["lon"] is not None
        assert station["height_m"] is not None
        assert station["sensor_type"]

    assert stations["KHWD08"]["metadata_status"] == "unavailable_not_pursued"
    assert stations["KHWD08"]["lat"] is None
    assert stations["KHWD08"]["lon"] is None


def test_v13_qpesums_config_does_not_mislabel_station_rainfall_as_radar():
    config = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config.yaml").read_text(encoding="utf-8"))
    qpesums = config["qpesums"]

    assert qpesums["enabled"] is False
    assert qpesums["source_status"] == "disabled_station_rainfall_qpe_fallback_only"
    assert qpesums["qpe_dataid"] is None
    assert qpesums["station_rainfall_fallback_dataid"] == "O-A0002-001"
    assert "O-A0059-001" in qpesums["radar_echo_dataid_candidates"]
    assert config["station_rainfall_qpe_fallback"]["dataid"] == "O-A0002-001"
    assert DATAID_STATION_RAINFALL_QPE == "O-A0002-001"
    assert DATAID_QPE == DATAID_STATION_RAINFALL_QPE


def test_v13_radar_grid_dataid_fails_until_parser_is_implemented():
    with pytest.raises(NotImplementedError):
        fetch_qpe_current(api_key="dummy", dataid="O-A0059-001")


def test_v13_zoning_documents_seasonal_wind_and_metadata_gap():
    zoning = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config" / "zoning.yaml").read_text(encoding="utf-8"))

    assert zoning["version"] == "v1.3"
    assert zoning["seasonal_prevalent_wind"]["summer"]["prevalent_direction"] == "W"
    assert zoning["metadata_gaps"][0]["station_id"] == "KHWD08"
    assert zoning["metadata_gaps"][0]["metadata_status"] == "unavailable_not_pursued"
    pairs = zoning["upstream_downstream_pairs"]
    seasons = {pair["season"]: pair for pair in pairs}
    assert seasons["summer"]["upstream_station_ids"] == ["C0V490", "C0V810"]
    assert seasons["summer"]["downstream_station_ids"] == ["KHWD04", "KHWD05", "KHWD06"]
    assert seasons["winter"]["upstream_station_ids"] == ["C0V810", "C0V890"]
    assert seasons["typhoon"]["upstream_station_ids"] == []
    paired_stations = {
        station_id
        for pair in pairs
        for station_id in [*pair["upstream_station_ids"], *pair["downstream_station_ids"]]
    }
    assert "KHWD08" not in paired_stations


def test_v13_features_and_horizons_are_split_from_main_config():
    config = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config.yaml").read_text(encoding="utf-8"))
    horizons = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config" / "horizons.yaml").read_text(encoding="utf-8"))
    features = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config" / "features.yaml").read_text(encoding="utf-8"))

    assert horizons["anchor_offsets_minutes"] == config["anchor_offsets_minutes"]
    assert horizons["horizon_minutes"] == config["horizon_minutes"]
    assert horizons["policy"]["horizon_decay_enabled"] is False
    assert features["leakage_policy"]["no_same_timestamp_cross_target_leakage_for_algorithm_benchmark"] is True
    assert features["benchmark_policy"]["wind_speed_current_algorithm"] == "random_forest"
    assert features["benchmark_policy"]["wind_gust_current_algorithm"] == "random_forest"


def test_v13_nearby_cwa_wind_algorithms_reverted_to_random_forest():
    config = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config.yaml").read_text(encoding="utf-8"))
    algorithms = config["nearby_cwa_historical_training"]["model_algorithms"]

    assert algorithms["wind_speed"]["primary_algorithm"] == "random_forest"
    assert algorithms["wind_gust"]["primary_algorithm"] == "random_forest"


def test_v13_tier_terminology_mapping_document_exists():
    text = (PROJECT_ROOT / "docs" / "tier_to_dispatch_risk_mapping.md").read_text(encoding="utf-8")

    assert "nearby_cwa_historical_model" in text
    assert "port_local_postprocess" in text
    assert "station_rainfall_qpe_fallback" in text
    assert "Tier 僅保留為教學性分類" in text


def test_v13_reference_only_contains_complete_cwa_marine_station_set():
    pool = yaml.safe_load((PROJECT_ROOT / "kaohsiung_microclimate_lstm" / "config" / "station_pool.yaml").read_text(encoding="utf-8"))
    stations = {
        str(station["station_id"]): station
        for station in pool["priority_groups"]["reference_only"]["stations"]
    }

    assert set(DEFAULT_STATION_IDS).issubset(stations)
    for station_id in DEFAULT_STATION_IDS:
        station = stations[station_id]
        assert station["source"] == "cwa_marine"
        assert station["role"] == "reference_only"
        assert station["is_port_local"] is False
        assert station["is_core_station"] is False
        assert station["lon"] is not None
        assert station["lat"] is not None


def test_v13_marine_payload_parser_maps_o_b0075_fields():
    payload = {
        "Records": {
            "SeaSurfaceObs": {
                "Location": [
                    {
                        "Station": {"StationID": "COMC08", "StationName": "Mituo"},
                        "StationObsTimes": {
                            "StationObsTime": [
                                {
                                    "DateTime": "2026-07-10T01:00:00+08:00",
                                    "WeatherElements": {
                                        "PrimaryAnemometer": {
                                            "WindSpeed": "7.4",
                                            "MaximumWindSpeed": "9.7",
                                            "WindDirection": "168",
                                        },
                                        "TideHeight": "0.31",
                                        "WaveHeight": "1.2",
                                        "WavePeriod": "5.6",
                                        "StationPressure": "1008.4",
                                        "SeaCurrents": {
                                            "Layer": {
                                                "CurrentSpeed": "0.43",
                                                "CurrentDirection": "210",
                                            }
                                        },
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        }
    }

    frame = marine_payload_to_frame(payload, station_ids=["COMC08"], fetched_at="2026-07-10T00:00:00+00:00")

    assert list(frame.columns) == MARINE_COLUMNS
    row = frame.iloc[0]
    assert row["station_id"] == "COMC08"
    assert row["wind_speed"] == 7.4
    assert row["wind_gust"] == 9.7
    assert row["wave_height"] == 1.2
    assert row["wave_period"] == 5.6
    assert row["current_speed"] == 0.43
    assert row["current_direction"] == 210.0
    assert row["air_pressure"] == 1008.4


def test_v13_marine_station_csv_uses_same_append_dedupe_contract(tmp_path):
    csv_path = tmp_path / "COMC08.csv"
    append_station_frame(
        csv_path,
        pd.DataFrame(
            [
                {
                    "station_id": "COMC08",
                    "obs_time": "2026-07-10T01:00:00+08:00",
                    "wave_height": 1.0,
                }
            ]
        ),
    )
    combined = append_station_frame(
        csv_path,
        pd.DataFrame(
            [
                {
                    "station_id": "COMC08",
                    "obs_time": "2026-07-10T01:00:00+08:00",
                    "wave_height": 1.2,
                },
                {
                    "station_id": "COMC08",
                    "obs_time": "2026-07-10T02:00:00+08:00",
                    "wave_height": 1.3,
                },
            ]
        ),
    )

    assert len(combined) == 2
    assert combined.loc[combined["obs_time"] == "2026-07-10T01:00:00+08:00", "wave_height"].iloc[0] == 1.2
