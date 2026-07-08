from kaohsiung_microclimate_lstm.src.postprocess.rain_probability_rules import apply_rain_probability_rules


CONFIG = {
    "nearby_precip": {
        "enabled": True,
        "single_station_trigger_mm": 0.5,
        "single_station_min_probability": 0.70,
        "mean_trigger_mm": 2.0,
        "mean_min_probability": 0.85,
        "dry_suppression_probability": 0.15,
    },
    "cwa_pop3h": {
        "enabled": True,
        "high_pop_trigger": 0.60,
        "high_pop_weight_for_rule": 0.80,
        "low_pop_trigger": 0.10,
    },
    "probability_clip": {"min": 0.0, "max": 1.0},
}


def test_rule1_nearby_single_station_trigger():
    raw = {"H1": 0.3, "H2": 0.2, "H3": 0.2, "H4": 0.2}
    nearby = {"max_1hr": 0.8, "mean_1hr": 0.3, "available": True}
    result = apply_rain_probability_rules(raw, nearby, {"available": False}, CONFIG)
    assert result["adjusted_probs"]["H1"] == 0.70
    assert result["adjusted_probs"]["H2"] == 0.70


def test_rule2_nearby_mean_trigger():
    raw = {"H1": 0.3, "H2": 0.2, "H3": 0.2, "H4": 0.2}
    nearby = {"max_1hr": 3.0, "mean_1hr": 2.5, "available": True}
    result = apply_rain_probability_rules(raw, nearby, {"available": False}, CONFIG)
    assert result["adjusted_probs"]["H1"] == 0.85
    assert result["adjusted_probs"]["H2"] == 0.85


def test_rule4_dry_suppression():
    raw = {"H1": 0.4, "H2": 0.3, "H3": 0.2, "H4": 0.2}
    nearby = {"max_1hr": 0.0, "mean_1hr": 0.0, "available": True}
    cwa = {"available": True, "current": 0.05}
    result = apply_rain_probability_rules(raw, nearby, cwa, CONFIG)
    assert result["adjusted_probs"]["H1"] <= 0.15
    assert result["adjusted_probs"]["H2"] <= 0.15
