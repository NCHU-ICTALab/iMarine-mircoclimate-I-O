import pandas as pd

from kaohsiung_microclimate_lstm.src.data.historical_weather_normalizer import normalize_historical_weather_frame


def test_historical_weather_normalizer_maps_codis_columns():
    raw = pd.DataFrame(
        {
            "ObsTime": ["2026-07-01 00:00", "2026-07-01 01:00"],
            "WS": [3.0, 4.0],
            "WD": [180, 190],
            "WSGust": [6.0, 7.0],
            "WDGust": [200, 210],
            "Precp": [0.0, 1.2],
            "RH": [80, 82],
        }
    )

    result = normalize_historical_weather_frame(raw, "C0V890")

    assert list(result["station_id"].unique()) == ["C0V890"]
    assert "wind_speed" in result.columns
    assert "wind_gust" in result.columns
    assert "precipitation_1hr" in result.columns
    assert result["precipitation_1hr"].iloc[1] == 1.2


def test_historical_weather_normalizer_converts_out_of_physical_range_sentinels_to_nan():
    raw = pd.DataFrame(
        {
            "ObsTime": ["2026-07-01 00:00", "2026-07-01 01:00"],
            "WS": [-99.7, 4.0],
            "WSGust": [-99.8, 7.0],
            "Precp": [-999.6, 1.2],
            "RH": [101.0, 82.0],
            "Tx": [-99.0, 28.0],
            "StnPres": [9999.0, 1008.5],
        }
    )

    result = normalize_historical_weather_frame(raw, "C0V890")

    assert pd.isna(result["wind_speed"].iloc[0])
    assert pd.isna(result["wind_gust"].iloc[0])
    assert pd.isna(result["precipitation_1hr"].iloc[0])
    assert pd.isna(result["relative_humidity"].iloc[0])
    assert pd.isna(result["temperature"].iloc[0])
    assert pd.isna(result["station_pressure"].iloc[0])
    assert result["wind_speed"].iloc[1] == 4.0
