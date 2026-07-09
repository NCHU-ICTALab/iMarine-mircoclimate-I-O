from kaohsiung_microclimate_lstm.src.data.port_local_station_normalizer import normalize_port_local_station_records


def test_khwd_raw_record_normalizes_to_canonical_columns():
    result = normalize_port_local_station_records(
        "KHWD01",
        "wind",
        [{"obs_time": "2026-07-08T10:00:00+08:00", "WS_AVG": "10", "WS_MAX": "12", "WD_AVG": "180"}],
        {},
    )

    record = result["records"][0]
    assert record["station_id"] == "KHWD01"
    assert record["station_type"] == "wind"
    assert record["wind_speed"] == 10.0
    assert record["wind_gust"] == 12.0
    assert record["wind_direction"] == 180.0
    assert "obs_time" in record


def test_normalizer_converts_knot_and_kmh_to_mps():
    knot = normalize_port_local_station_records(
        "KHWD01",
        "wind",
        [{"obs_time": "2026-07-08T10:00:00+08:00", "wind_speed": 10, "wind_gust": 20, "wind_direction": 90, "wind_unit": "knot"}],
        {},
    )
    kmh = normalize_port_local_station_records(
        "KHWD01",
        "wind",
        [{"obs_time": "2026-07-08T10:00:00+08:00", "wind_speed": 36, "wind_gust": 72, "wind_direction": 90, "wind_unit": "km/h"}],
        {},
    )

    assert round(knot["records"][0]["wind_speed"], 3) == 5.144
    assert kmh["records"][0]["wind_speed"] == 10.0


def test_tide_and_wave_records_normalize_units():
    tide = normalize_port_local_station_records(
        "KHTD01",
        "tide",
        [{"obs_time": "2026-07-08T10:00:00+08:00", "tide_level": 1.2, "tide_unit": "m"}],
        {},
    )
    wave = normalize_port_local_station_records(
        "KHAW01",
        "wave_current",
        [{"obs_time": "2026-07-08T10:00:00+08:00", "wave_height": 120, "wave_unit": "cm", "wave_period_s": 8, "current_speed": 0.5, "current_direction": 30}],
        {},
    )

    assert tide["records"][0]["tide_level_cm"] == 120.0
    assert wave["records"][0]["wave_height_m"] == 1.2


def test_parse_error_does_not_crash_normalizer():
    result = normalize_port_local_station_records("KHWD01", "wind", [{"obs_time": "not-a-time", "WS_AVG": "bad"}], {})

    assert result["normalization_status"] in {"degraded", "unavailable"}
    assert isinstance(result["warnings"], list)
