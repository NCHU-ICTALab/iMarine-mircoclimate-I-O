from kaohsiung_microclimate_lstm.src.data.station_metadata_validator import validate_station_metadata


def _pool(is_port_local_467441=False, core_467441=False):
    return {
        "station_pool_version": "v2.7",
        "priority_groups": {
            "port_local_wind": {
                "priority": 1,
                "stations": [
                    {"station_id": "KHWD01", "is_port_local": True, "is_core_station": True, "role": "port_local_wind_station"},
                ],
            },
            "fallback_baseline": {
                "priority": 5,
                "stations": [
                    {
                        "station_id": "467441",
                        "is_port_local": is_port_local_467441,
                        "is_core_station": core_467441,
                        "role": "fallback_baseline",
                        "usage": "fallback_only",
                    },
                ],
            },
        },
    }


def test_station_metadata_validator_reports_available_and_missing_stations():
    report = validate_station_metadata(_pool(), ["KHWD01.csv", "467441.csv", "UNKNOWN.csv"])

    assert report["is_valid"] is True
    assert report["valid_port_local_stations"] == ["KHWD01"]
    assert report["fallback_stations"] == ["467441"]
    assert report["unknown_station_ids"] == ["UNKNOWN"]


def test_station_metadata_validator_rejects_467441_as_port_local_core():
    report = validate_station_metadata(_pool(is_port_local_467441=True, core_467441=True), ["467441.csv"])

    assert report["is_valid"] is False
    assert any("467441" in reason for reason in report["invalid_reasons"])
