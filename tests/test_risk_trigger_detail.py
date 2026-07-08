from kaohsiung_microclimate_lstm.src.risk.risk_trigger_detail import build_risk_trigger_detail


RELIABILITY = {
    "rain_probability": "low_to_medium",
    "wind_speed": "high",
    "wind_gust": "medium_high",
    "visibility": "unavailable",
    "tide": "reference_only",
}


def test_rain_trigger_when_only_rain_is_watch():
    detail = build_risk_trigger_detail("watch", "watch", "normal", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "rain_probability"
    assert detail["is_low_reliability_trigger"] is True


def test_wind_speed_beats_lower_rain():
    detail = build_risk_trigger_detail("warning", "watch", "warning", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "wind_speed"
    assert detail["is_low_reliability_trigger"] is False


def test_gust_priority_breaks_tie():
    detail = build_risk_trigger_detail("warning", "normal", "warning", "warning", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "wind_gust"


def test_normal_risk_has_no_primary_trigger():
    detail = build_risk_trigger_detail("normal", "normal", "normal", "normal", None, None, RELIABILITY)
    assert detail["primary_trigger"] == "none"
    assert detail["primary_trigger_level"] == "normal"
    assert detail["primary_trigger_reliability"] is None
    assert detail["is_low_reliability_trigger"] is False
