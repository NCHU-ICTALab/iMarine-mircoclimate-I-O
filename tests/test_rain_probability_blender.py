import pytest

from kaohsiung_microclimate_lstm.src.forecast.rain_probability_blender import blend_with_cwa_pop3h


CONFIG = {
    "blending": {
        "enabled": True,
        "H1": {"lstm_weight": 1.0, "cwa_weight": 0.0},
        "H2": {"lstm_weight": 1.0, "cwa_weight": 0.0},
        "H3": {"lstm_weight": 0.5, "cwa_weight": 0.5, "cwa_source": "current"},
        "H4": {"lstm_weight": 0.3, "cwa_weight": 0.7, "cwa_source": "next"},
    },
    "probability_clip": {"min": 0.0, "max": 1.0},
}


def test_h3_h4_cwa_blending():
    probs = {"H1": 0.7, "H2": 0.7, "H3": 0.4, "H4": 0.35}
    cwa = {"available": True, "current": 0.6, "next": 0.8}
    result = blend_with_cwa_pop3h(probs, cwa, CONFIG)
    assert result["final_probs"]["H1"] == 0.7
    assert result["final_probs"]["H2"] == 0.7
    assert result["final_probs"]["H3"] == 0.5
    assert result["final_probs"]["H4"] == pytest.approx(0.665)


def test_cwa_unavailable_fallback():
    probs = {"H1": 0.7, "H2": 0.7, "H3": 0.4, "H4": 0.35}
    result = blend_with_cwa_pop3h(probs, {"available": False}, CONFIG)
    assert result["final_probs"] == probs
    assert result["cwa_blending_applied"] is False
