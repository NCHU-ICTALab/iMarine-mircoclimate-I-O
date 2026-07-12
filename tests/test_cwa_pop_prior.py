import pytest

from kaohsiung_microclimate_lstm.src.postprocess.cwa_pop_prior import apply_cwa_pop_prior


CONFIG = {
    "cwa_pop": {
        "enabled": True,
        "allowed_in_model_input": False,
        "weight_profile": "conservative",
        "profiles": {
            "conservative": {
                "apply_anchors": ["H3", "H4"],
                "weights": {
                    "H1": {"own_weight": 1.0, "cwa_weight": 0.0},
                    "H2": {"own_weight": 1.0, "cwa_weight": 0.0},
                    "H3": {"own_weight": 0.8, "cwa_weight": 0.2},
                    "H4": {"own_weight": 0.8, "cwa_weight": 0.2},
                },
            },
            "graduated_like_wind": {
                "apply_anchors": ["H1", "H2", "H3", "H4"],
                "weights": {
                    "H1": {"own_weight": 0.8, "cwa_weight": 0.2},
                    "H2": {"own_weight": 0.6, "cwa_weight": 0.4},
                    "H3": {"own_weight": 0.4, "cwa_weight": 0.6},
                    "H4": {"own_weight": 0.2, "cwa_weight": 0.8},
                },
            },
        },
    }
}


def test_cwa_unavailable_keeps_model_probability():
    probs = {"H1": 0.2, "H2": 0.3, "H3": 0.4, "H4": 0.5}
    result = apply_cwa_pop_prior(probs, {"available": False}, CONFIG)
    assert result["final_probabilities"] == probs
    assert result["trace"]["cwa_pop_used_as_postprocess_prior"] is False


def test_cwa_prior_defaults_to_conservative_profile():
    probs = {"H1": 0.2, "H2": 0.3, "H3": 0.4, "H4": 0.5}
    result = apply_cwa_pop_prior(probs, {"available": True, "current": 0.8, "next": 0.9}, CONFIG)

    assert result["final_probabilities"]["H1"] == 0.2
    assert result["final_probabilities"]["H2"] == 0.3
    assert result["final_probabilities"]["H3"] == pytest.approx(0.48)
    assert result["final_probabilities"]["H4"] == pytest.approx(0.58)
    assert result["trace"]["weight_profile"] == "conservative"
    assert result["trace"]["adjusted_anchors"] == ["H3", "H4"]
    assert result["source_detail"]["H1"]["cwa_prior_applied"] is False
    assert result["source_detail"]["H2"]["cwa_prior_applied"] is False
    assert result["source_detail"]["H3"]["cwa_weight"] == 0.2
    assert result["source_detail"]["H4"]["cwa_weight"] == 0.2


def test_cwa_prior_can_use_graduated_like_wind_candidate_profile():
    probs = {"H1": 0.2, "H2": 0.3, "H3": 0.4, "H4": 0.5}
    config = {"cwa_pop": {**CONFIG["cwa_pop"], "weight_profile": "graduated_like_wind"}}
    result = apply_cwa_pop_prior(probs, {"available": True, "current": 0.8, "next": 0.9}, config)

    assert result["final_probabilities"]["H1"] == pytest.approx(0.32)
    assert result["final_probabilities"]["H2"] == pytest.approx(0.5)
    assert result["final_probabilities"]["H3"] == pytest.approx(0.64)
    assert result["final_probabilities"]["H4"] == pytest.approx(0.82)
    assert result["trace"]["weight_profile"] == "graduated_like_wind"
    assert result["trace"]["adjusted_anchors"] == ["H1", "H2", "H3", "H4"]
    assert result["source_detail"]["H1"]["cwa_weight"] == 0.2
    assert result["source_detail"]["H4"]["cwa_weight"] == 0.8
