from kaohsiung_microclimate_lstm.src.cwa.location_resolver import resolve_cwa_forecast_source


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_dataset(self, dataset_id, location_name=None, element_name=None, force_refresh=False):
        if dataset_id == "A" and location_name == "前鎮區" and element_name == "PoP3h":
            return {
                "available": True,
                "dataset_id": dataset_id,
                "location_name": location_name,
                "element_name": element_name,
                "json": {
                    "records": {
                        "Locations": [
                            {
                                "Location": [
                                    {
                                        "LocationName": "前鎮區",
                                        "WeatherElement": [
                                            {
                                                "ElementName": "PoP3h",
                                                "Time": [
                                                    {
                                                        "StartTime": "2026-07-07T21:00:00+08:00",
                                                        "EndTime": "2026-07-08T00:00:00+08:00",
                                                        "ElementValue": [{"Value": "50"}],
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                },
                "fetched_at": "now",
            }
        return {"available": False, "reason": "no data"}


def test_resolver_selects_available_source(monkeypatch):
    import kaohsiung_microclimate_lstm.src.cwa.location_resolver as resolver

    monkeypatch.setattr(resolver, "CwaOpenDataClient", FakeClient)
    result = resolve_cwa_forecast_source(
        [{"dataset_id": "A", "priority": 1}],
        ["前鎮區"],
        {"precipitation_probability": ["PoP3h"]},
        "key",
        {"cwa_open_data": {}},
    )
    assert result["available"] is True
    assert result["source_resolution"] == "3h"
