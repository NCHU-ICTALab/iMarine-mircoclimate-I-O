from kaohsiung_microclimate_lstm.src.data.fetch_nearby_cwa_current import fetch_nearby_cwa_current


class _FailingResponse:
    def raise_for_status(self):
        raise RuntimeError("boom")


class _FailingSession:
    def get(self, *args, **kwargs):
        return _FailingResponse()


class _SuccessfulResponse:
    def __init__(self, station_id: str):
        self.station_id = station_id

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "records": {
                "Station": [
                    {
                        "StationName": self.station_id,
                        "ObsTime": {"DateTime": "2026-07-16T10:00:00+08:00"},
                        "WeatherElement": {
                            "WindSpeed": "2.3",
                            "WindDirection": "240",
                            "GustInfo": {"PeakGustSpeed": "4.5"},
                            "Now": {"Precipitation": "0.0"},
                        },
                    }
                ]
            }
        }


class _PartiallyFailingSession:
    def __init__(self, failing_station_ids: set[str]):
        self.failing_station_ids = failing_station_ids

    def get(self, *args, **kwargs):
        station_id = kwargs["params"]["StationId"]
        if station_id in self.failing_station_ids:
            return _FailingResponse()
        return _SuccessfulResponse(station_id)


def test_fetch_nearby_cwa_current_reports_all_station_failure(tmp_path):
    result = fetch_nearby_cwa_current(
        api_key="test-key",
        station_ids=["C0V890", "C0V490"],
        output_dir=tmp_path,
        append=True,
        session=_FailingSession(),
        verify_ssl=False,
    )

    assert result["rows_fetched"] == 0
    assert result["all_stations_failed"] is True
    assert result["per_station_status"]["C0V890"].startswith("error:")
    assert result["output_files"] == {}


def test_fetch_nearby_cwa_current_partial_failure_is_not_all_failed(tmp_path):
    result = fetch_nearby_cwa_current(
        api_key="test-key",
        station_ids=["C0V890", "C0V490", "C0V840"],
        output_dir=tmp_path,
        append=True,
        session=_PartiallyFailingSession({"C0V490"}),
        verify_ssl=False,
    )

    assert result["rows_fetched"] == 2
    assert result["all_stations_failed"] is False
    assert result["per_station_status"]["C0V890"] == "ok"
    assert result["per_station_status"]["C0V490"].startswith("error:")
    assert result["per_station_status"]["C0V840"] == "ok"
    assert set(result["output_files"]) == {"C0V890", "C0V840"}
