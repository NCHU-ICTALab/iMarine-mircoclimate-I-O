import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from kaohsiung_microclimate_lstm.src.data.log_cwa_forecast_history import (
    build_cwa_comparison_readiness_report,
    write_cwa_forecast_snapshot,
)


TAIPEI = timezone(timedelta(hours=8))


def test_write_cwa_forecast_snapshot_uses_data_id_directory(tmp_path):
    path = write_cwa_forecast_snapshot(
        {"records": {"location": []}},
        data_id="F-D0047-091",
        output_root=tmp_path,
        fetched_at=datetime(2026, 7, 10, 12, 0, tzinfo=TAIPEI),
    )

    assert path.name == "20260710_1200.json"
    assert path.parent.name == "F-D0047-091"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["data_id"] == "F-D0047-091"


def test_cwa_comparison_readiness_blocks_until_14_days(tmp_path):
    history_root = tmp_path / "history"
    obs_root = tmp_path / "observed"
    obs_root.mkdir()
    for day in range(3):
        write_cwa_forecast_snapshot(
            {"day": day},
            output_root=history_root,
            fetched_at=datetime(2026, 7, 1 + day, 12, 0, tzinfo=TAIPEI),
        )
    pd.DataFrame({"obs_time": pd.date_range("2026-07-01", periods=3, freq="1D", tz=TAIPEI)}).to_csv(
        obs_root / "C0V890.csv",
        index=False,
    )

    report = build_cwa_comparison_readiness_report(history_root, obs_root, tmp_path / "reports", min_days=14)

    assert report["ready"] is False
    assert report["comparison_report_allowed"] is False
    assert (tmp_path / "reports" / "comparison_readiness_report.json").exists()
