from kaohsiung_microclimate_lstm.src.data.twport_realtime_parser import (
    canonical_khwd_station_id,
    parse_twport_realtime_wind_records,
)


def test_parse_khwd_realtime_block_and_canonicalize_raw_sensor_id():
    text = """
    KHWD01
    KHWD01M01
    WS_AVG=3.336
    WD_AVG=282
    WS_MAX=6.53
    WD_MAX=271
    MAX_T=2026-06-02 13:54:00
    """

    records = parse_twport_realtime_wind_records(text, ["KHWD01"])

    assert canonical_khwd_station_id("KHWD01M01") == "KHWD01"
    assert records == [
        {
            "station_id": "KHWD01",
            "station_type": "wind",
            "timestamp": "2026-06-02T13:54:00+08:00",
            "obs_time": "2026-06-02T13:54:00+08:00",
            "wind_speed": 3.336,
            "wind_direction": 282.0,
            "wind_gust": 6.53,
            "wind_gust_direction": 271.0,
            "raw_station_ref": "KHWD01M01",
            "source": "twport_realtime_panel",
            "quality_flag": "ok",
            "raw_data": {"WS_AVG": 3.336, "WD_AVG": 282.0, "WS_MAX": 6.53, "WD_MAX": 271.0, "MAX_T": "2026-06-02 13:54:00"},
        }
    ]


def test_parser_accepts_m10_and_other_raw_ids():
    text = """
    KHWD04M10 WS_AVG=2.1 WD_AVG=180 WS_MAX=4.2 WD_MAX=200 MAX_T=2026/06/02 13:50:00
    KHWD05XYZ WS_AVG=1.1 WD_AVG=90 WS_MAX=2.2 WD_MAX=100 MAX_T=2026/06/02 13:40:00
    """

    records = parse_twport_realtime_wind_records(text, ["KHWD04", "KHWD05"])

    assert [record["station_id"] for record in records] == ["KHWD04", "KHWD05"]
    assert records[0]["raw_station_ref"] == "KHWD04M10"
    assert records[1]["raw_station_ref"] == "KHWD05XYZ"


def test_parser_prefers_latest_then_more_complete_record():
    text = """
    KHWD06M01 WS_AVG=1 WD_AVG=100 MAX_T=2026-06-02 13:54:00
    KHWD06M10 WS_AVG=2 WD_AVG=110 WS_MAX=5 WD_MAX=120 MAX_T=2026-06-02 13:54:00
    KHWD07M01 WS_AVG=3 WD_AVG=130 WS_MAX=6 WD_MAX=140 MAX_T=2026-06-02 13:40:00
    KHWD07M10 WS_AVG=4 WD_AVG=150 WS_MAX=7 WD_MAX=160 MAX_T=2026-06-02 13:59:00
    """

    records = parse_twport_realtime_wind_records(text, ["KHWD06", "KHWD07"])
    by_id = {record["station_id"]: record for record in records}

    assert by_id["KHWD06"]["raw_station_ref"] == "KHWD06M10"
    assert by_id["KHWD07"]["raw_station_ref"] == "KHWD07M10"


def test_parser_degrades_without_timestamp_and_allows_missing_gust():
    text = """
    KHWD08M01
    WS_AVG=3.0
    WD_AVG=200
    """

    records = parse_twport_realtime_wind_records(text, ["KHWD08"])

    assert records[0]["timestamp"] is None
    assert records[0]["wind_gust"] is None
    assert records[0]["quality_flag"] == "missing_gust"
