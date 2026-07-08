import pytest

from kaohsiung_microclimate_lstm.src.postprocess.cwa_pop_prior import apply_cwa_pop_prior


CONFIG = {
    "cwa_pop": {
        "enabled": True,
        "allowed_in_model_input": False,
        "max_adjustment_weight": 0.2,
        "apply_anchors": ["H3", "H4"],
    }
}


def test_cwa_unavailable_keeps_model_probability():
    probs = {"H1": 0.2, "H2": 0.3, "H3": 0.4, "H4": 0.5}
    result = apply_cwa_pop_prior(probs, {"available": False}, CONFIG)
    assert result["final_probabilities"] == probs
    assert result["trace"]["cwa_pop_used_as_postprocess_prior"] is False


def test_cwa_prior_applies_only_h3_h4_with_capped_weight():
    probs = {"H1": 0.2, "H2": 0.3, "H3": 0.4, "H4": 0.5}
    config = {"cwa_pop": {**CONFIG["cwa_pop"], "max_adjustment_weight": 0.9}}
    result = apply_cwa_pop_prior(probs, {"available": True, "current": 0.8, "next": 0.9}, config)
    assert result["final_probabilities"]["H1"] == 0.2
    assert result["final_probabilities"]["H2"] == 0.3
    assert result["final_probabilities"]["H3"] == pytest.approx(0.48)
    assert result["final_probabilities"]["H4"] == pytest.approx(0.58)
    assert result["trace"]["weight"] == 0.2
    assert result["trace"]["adjusted_anchors"] == ["H3", "H4"]
