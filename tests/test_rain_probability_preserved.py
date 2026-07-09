from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_v29_rain_probability_report_preserves_all_anchor_fields():
    result = {
        "forecast_anchors": [
            {
                "label": "H1",
                "rain": {
                    "raw_model_probability": 0.3,
                    "nearby_adjusted_probability": 0.3,
                    "port_local_adjusted_probability": None,
                    "cwa_adjusted_probability": None,
                    "final_probability": 0.3,
                    "level": "watch",
                    "confidence": "low_to_medium",
                    "source_detail": {"model_used": True},
                },
            }
        ]
    }

    report = predict_module._build_v29_rain_probability_report(result, {"cwa_pop_prior": {"enabled": True}})

    assert report["rain_probability_preserved"] is True
    assert report["rain_probability_model_used"] is True
    assert report["anchors"]["H1"]["final_probability"] == 0.3
    assert report["anchors"]["H1"]["source_detail"]["model_used"] is True
