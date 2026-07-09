from kaohsiung_microclimate_lstm.src.data.nearby_station_ranker import rank_nearby_cwa_stations


def test_nearby_station_ranker_selects_stations_closer_than_467441():
    stations = [
        {"station_id": "C0V890", "name": "Qianzhen", "longitude": 120.3117, "latitude": 22.5718},
        {"station_id": "C0V490", "name": "Gushan", "longitude": 120.298803, "latitude": 22.627422},
        {"station_id": "467441", "name": "Kaohsiung", "longitude": 120.312516, "latitude": 22.730432},
    ]
    points = [{"name": "qianzhen", "longitude": 120.304, "latitude": 22.574}]
    cfg = {"nearby_cwa_historical_training": {"priority_1_station_ids": ["C0V890", "C0V490"], "max_selected_stations": 6}}

    result = rank_nearby_cwa_stations(stations, points, "467441", cfg)

    assert result["baseline_distance_km"] > 0
    assert result["selected_station_ids"] == ["C0V890", "C0V490"]
    assert result["ranking_report"]["all_selected_stations_closer_than_467441"] is True
