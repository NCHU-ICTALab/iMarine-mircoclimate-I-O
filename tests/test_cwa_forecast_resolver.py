from kaohsiung_microclimate_lstm.src.cwa.location_resolver import resolve_cwa_forecast_source


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_dataset(self, dataset_id, location_name=None, element_name=None, force_refresh=False):
        if dataset_id in {"A", "F-D0047-065", "F-D0047-091"} and location_name == "前鎮區" and element_name in {"PoP3h", "3小時降雨機率"}:
            end_time = "2026-07-08T00:00:00+08:00" if dataset_id != "F-D0047-091" else "2026-07-08T03:00:00+08:00"
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
                                                        "EndTime": end_time,
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


def test_resolver_selects_verified_3h_dataset_over_misleading_element_name(monkeypatch):
    import kaohsiung_microclimate_lstm.src.cwa.location_resolver as resolver

    monkeypatch.setattr(resolver, "CwaOpenDataClient", FakeClient)
    result = resolve_cwa_forecast_source(
        [
            {"dataset_id": "F-D0047-091", "priority": 1},
            {"dataset_id": "F-D0047-065", "priority": 2},
        ],
        ["前鎮區"],
        {"precipitation_probability": ["3小時降雨機率"]},
        "key",
        {"cwa_open_data": {}},
    )

    assert result["dataset_id"] == "F-D0047-065"
    assert result["source_resolution"] == "3h"
    tested_091 = next(item for item in result["tested"] if item["dataset_id"] == "F-D0047-091")
    assert tested_091["source_resolution"] == "6h"
