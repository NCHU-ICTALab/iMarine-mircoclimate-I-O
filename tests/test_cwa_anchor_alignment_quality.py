from datetime import datetime
from zoneinfo import ZoneInfo

from kaohsiung_microclimate_lstm.src.cwa.cwa_pop_quality import align_cwa_pop_quality_to_anchors


SOURCE = {"dataset_id": "D", "location_name": "前鎮區", "element_name": "PoP3h", "source_resolution": "3h"}


def test_anchor_quality_matched_zero_is_valid():
    rows = [{"start_time": "2026-07-07T21:00:00+08:00", "end_time": "2026-07-08T00:00:00+08:00", "raw_value": "0", "pop": 0.0}]
    quality = align_cwa_pop_quality_to_anchors(rows, datetime(2026, 7, 7, 22, 0, tzinfo=ZoneInfo("Asia/Taipei")), {"H1": 30}, SOURCE)
    assert quality["H1"]["available"] is True
    assert quality["H1"]["normalized_value"] == 0.0
    assert quality["H1"]["alignment_status"] == "matched_forecast_period"


def test_anchor_quality_no_matching_period_is_invalid():
    rows = [{"start_time": "2026-07-07T21:00:00+08:00", "end_time": "2026-07-07T22:00:00+08:00", "raw_value": "20", "pop": 0.2}]
    quality = align_cwa_pop_quality_to_anchors(rows, datetime(2026, 7, 7, 22, 0, tzinfo=ZoneInfo("Asia/Taipei")), {"H1": 30}, SOURCE)
    assert quality["H1"]["available"] is False
    assert quality["H1"]["alignment_status"] == "no_matching_forecast_period"


def test_anchor_quality_empty_timeseries():
    quality = align_cwa_pop_quality_to_anchors([], datetime(2026, 7, 7, 22, 0, tzinfo=ZoneInfo("Asia/Taipei")), {"H1": 30}, SOURCE)
    assert quality["H1"]["available"] is False
    assert quality["H1"]["alignment_status"] == "no_forecast_timeseries"
