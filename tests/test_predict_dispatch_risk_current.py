from kaohsiung_microclimate_lstm.src import predict as predict_module


def test_predict_dispatch_risk_current_delegates_to_current_version(monkeypatch):
    calls = {}

    def fake_current(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {"model_version": "current", "target_area": kwargs.get("target_area")}

    monkeypatch.setattr(predict_module, "predict_dispatch_risk_v35", fake_current)

    result = predict_module.predict_dispatch_risk_current(target_area="KHH")

    assert result == {"model_version": "current", "target_area": "KHH"}
    assert calls["kwargs"]["target_area"] == "KHH"
