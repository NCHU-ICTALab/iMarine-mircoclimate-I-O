from kaohsiung_microclimate_lstm.src.risk.risk_trigger_detail import build_risk_trigger_detail


RELIABILITY = {
    "rain_probability": "low_to_medium",
    "wind_speed": "high",
    "wind_gust": "medium_high",
    "visibility": "unavailable",
    "tide": "reference_only",
}


def test_all_normal_uses_none_trigger():
    detail = build_risk_trigger_detail("normal", "normal", "normal", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "none"
    assert detail["primary_trigger_level"] == "normal"
    assert detail["primary_trigger_reliability"] is None
    assert detail["is_low_reliability_trigger"] is False
    assert detail["primary_trigger"] not in {"wind_gust", "wind_speed", "rain_probability"}


def test_rain_watch_uses_rain_trigger():
    detail = build_risk_trigger_detail("watch", "watch", "normal", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "rain_probability"
    assert detail["primary_trigger_reliability"] == "low_to_medium"
    assert detail["is_low_reliability_trigger"] is True


def test_wind_warning_beats_lower_rain():
    detail = build_risk_trigger_detail("warning", "watch", "warning", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "wind_speed"
    assert detail["primary_trigger_reliability"] == "high"
    assert detail["is_low_reliability_trigger"] is False


def test_gust_warning_priority_breaks_tie():
    detail = build_risk_trigger_detail("warning", "watch", "warning", "warning", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "wind_gust"
    assert detail["primary_trigger_reliability"] == "medium_high"
