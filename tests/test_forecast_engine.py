from datetime import datetime, timedelta

from microclimate.forecast_engine import build_forecast
from microclimate.models import Observation, UTC


def test_build_forecast_prefers_source_a_and_projects_trend():
    now = datetime.now(UTC)
    history = [
        Observation("b1", "小港", now - timedelta(minutes=60), "B", wind_speed=3),
        Observation("b1", "小港", now, "B", wind_speed=4),
        Observation("a1", "高雄港", now - timedelta(minutes=60), "A", wind_speed=5),
        Observation("a1", "高雄港", now, "A", wind_speed=7),
    ]

    forecasts = build_forecast(history, minutes=30)

    assert {item.source for item in forecasts} == {"A"}
    assert [item.is_forecast for item in forecasts] == [False, True, True, True]
    assert forecasts[-1].wind_speed == 8.0
    assert forecasts[-1].confidence == "medium"
