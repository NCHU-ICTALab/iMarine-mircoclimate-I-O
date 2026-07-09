from kaohsiung_microclimate_lstm.src.data.station_pool import enabled_input_stations


def test_enabled_input_stations_filters_disabled_and_keeps_target():
    config = {
        "selection_rules": {"include_enabled_only": True},
        "input_stations": [
            {"station_id": "467441", "enabled": True, "required": True},
            {"station_id": "C4Q01", "enabled": True},
            {"station_id": "C4Q02", "enabled": False},
        ],
    }

    stations = enabled_input_stations(config)

    assert [station["station_id"] for station in stations] == ["467441", "C4Q01"]
    assert stations[0]["required"] is True
