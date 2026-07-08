from kaohsiung_microclimate_lstm.src.risk.action_mapping import map_dispatch_action_level


def test_action_mapping_degrades_low_reliability():
    assert map_dispatch_action_level("normal", "high")["dispatch_action_level"] == "normal_dispatch"
    assert map_dispatch_action_level("watch", "low_to_medium")["dispatch_action_level"] == "observe_only"
    assert map_dispatch_action_level("watch", "high")["dispatch_action_level"] == "monitor"
    assert map_dispatch_action_level("warning", "low_to_medium")["dispatch_action_level"] == "monitor"
    assert map_dispatch_action_level("warning", "high")["dispatch_action_level"] == "restrict_sensitive_tasks"
    assert map_dispatch_action_level("high_risk", "medium_high")["dispatch_action_level"] == "delay_high_risk_tasks"
    assert map_dispatch_action_level("stop", "high")["dispatch_action_level"] == "suspend_exposed_tasks"
