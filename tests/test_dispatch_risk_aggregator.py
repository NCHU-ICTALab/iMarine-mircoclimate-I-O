from kaohsiung_microclimate_lstm.src.risk.dispatch_risk_aggregator import aggregate_dispatch_risk, dispatch_suggestion


def test_aggregates_max_weather_level():
    result = aggregate_dispatch_risk(
        {"H1": "normal", "H2": "watch"},
        {"H1": "warning", "H2": "normal"},
        {"H1": "watch", "H2": "high_risk"},
    )
    assert result == {"H1": "warning", "H2": "high_risk"}


def test_optional_sources_can_be_unavailable():
    result = aggregate_dispatch_risk({"H1": "normal"}, {"H1": "normal"}, {"H1": "normal"}, None, None)
    assert result["H1"] == "normal"


def test_stop_level_wins():
    result = aggregate_dispatch_risk({"H1": "high_risk"}, {"H1": "stop"}, {"H1": "normal"})
    assert result["H1"] == "stop"
    assert "停止" in dispatch_suggestion("stop")
