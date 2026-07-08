from datetime import datetime
from zoneinfo import ZoneInfo

from kaohsiung_microclimate_lstm.src.cwa.cwa_open_data_client import align_cwa_pop_to_anchors, extract_pop_timeseries


def test_extract_pop_timeseries_normalizes_percent():
    body = {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "LocationName": "前鎮區",
                            "WeatherElement": [
                                {
                                    "ElementName": "3小時降雨機率",
                                    "Time": [
                                        {
                                            "StartTime": "2026-07-07T21:00:00+08:00",
                                            "EndTime": "2026-07-08T00:00:00+08:00",
                                            "ElementValue": [{"ProbabilityOfPrecipitation": "40"}],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    }
    rows = extract_pop_timeseries(body, "前鎮區", "3小時降雨機率")
    assert rows[0]["pop"] == 0.4


def test_align_cwa_pop_to_anchors():
    rows = [{"start_time": "2026-07-07T21:00:00+08:00", "end_time": "2026-07-08T00:00:00+08:00", "pop": 0.4}]
    generated_at = datetime(2026, 7, 7, 22, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    aligned = align_cwa_pop_to_anchors(rows, generated_at, {"H1": 30, "H2": 60, "H3": 90, "H4": 120})
    assert aligned == {"H1": 0.4, "H2": 0.4, "H3": 0.4, "H4": None}
