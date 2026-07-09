from kaohsiung_microclimate_lstm.src.station_usage import build_current_station_usage, build_station_display_rows


def _result(mode):
    return {
        "prediction_mode": mode,
        "station_priority_summary": {"port_local_station_ids": ["KHWD01", "KHWD04"]},
        "nearby_cwa_historical_summary": {
            "model_accepted": True,
            "selected_station_ids": ["C0V890", "C0V490"],
        },
        "trace": {"nearby_cwa_selected_station_ids": ["C0V890", "C0V490"]},
    }


def test_v34_normal_mode_uses_khwd_station_rows(tmp_path):
    result = _result("port_local_postprocess")
    usage = build_current_station_usage(result, {})
    result["current_station_usage"] = usage
    rows = build_station_display_rows(result, {}, tmp_path)

    assert usage["port_local_station_ids_used"] == ["KHWD01", "KHWD04"]
    assert usage["nearby_cwa_station_ids_used_for_current_prediction"] == []
    khwd_rows = [row for row in rows if row["station_group"] == "KHWD"]
    assert any(row["used_for_current_prediction"] is True for row in khwd_rows)
    assert all(row["is_port_local_core"] is True for row in khwd_rows)


def test_v34_no_realtime_mode_uses_nearby_cwa_rows(tmp_path):
    result = _result("nearby_cwa_historical_model")
    usage = build_current_station_usage(result, {})
    result["current_station_usage"] = usage
    rows = build_station_display_rows(result, {}, tmp_path)

    assert usage["port_local_station_ids_used"] == []
    assert usage["nearby_cwa_station_ids_used_for_current_prediction"] == ["C0V890", "C0V490"]
    nearby_rows = [row for row in rows if row["station_group"] == "nearby_cwa"]
    assert all(row["is_port_local_core"] is False for row in nearby_rows)
    assert any(row["used_for_current_prediction"] is True for row in nearby_rows)


def test_v34_467441_is_never_core_station(tmp_path):
    result = _result("fallback_baseline")
    usage = build_current_station_usage(result, {})
    result["current_station_usage"] = usage
    rows = build_station_display_rows(result, {}, tmp_path)

    baseline = [row for row in rows if row["station_id"] == "467441"][0]
    assert baseline["used_for_current_prediction"] is True
    assert baseline["is_port_local_core"] is False
