from kaohsiung_microclimate_lstm.src.data.station_pool import flatten_priority_station_pool


def _pool():
    return {
        "priority_groups": {
            "port_local_wind": {
                "priority": 1,
                "required_for_core_prediction": True,
                "stations": [
                    {"station_id": "KHWD01", "role": "port_local_wind_station", "is_port_local": True, "is_core_station": True},
                ],
            },
            "fallback_baseline": {
                "priority": 5,
                "stations": [
                    {"station_id": "467441", "role": "fallback_baseline", "is_port_local": False, "is_core_station": False, "usage": "fallback_only"},
                ],
            },
        }
    }


def test_station_priority_keeps_467441_out_of_core_group():
    stations = flatten_priority_station_pool(_pool())
    by_id = {station["station_id"]: station for station in stations}

    assert by_id["KHWD01"]["is_port_local"] is True
    assert by_id["KHWD01"]["priority_group"] == "port_local_wind"
    assert by_id["467441"]["is_port_local"] is False
    assert by_id["467441"]["is_core_station"] is False
    assert by_id["467441"]["priority_group"] == "fallback_baseline"
