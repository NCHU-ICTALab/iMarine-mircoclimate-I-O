from __future__ import annotations

import pandas as pd

from kaohsiung_microclimate_lstm.src.tools.report_surge_residual_readiness import report_surge_residual_readiness


def test_surge_residual_readiness_blocks_when_history_is_too_short(tmp_path):
    observed = tmp_path / "observed"
    observed.mkdir()
    pd.DataFrame(
        {
            "station_id": ["C4P01", "C4P01"],
            "obs_time": ["2026-07-10T00:00:00+08:00", "2026-07-10T01:00:00+08:00"],
            "tide_level": [10.0, 11.0],
        }
    ).to_csv(observed / "C4P01.csv", index=False)
    pd.DataFrame(
        {
            "station_id": ["COMC08", "COMC08"],
            "obs_time": ["2026-07-10T00:00:00+08:00", "2026-07-10T01:00:00+08:00"],
            "wave_height": [1.2, 1.3],
            "wave_period": [5.0, 5.2],
        }
    ).to_csv(observed / "COMC08.csv", index=False)

    report = report_surge_residual_readiness(
        observed_dir=observed,
        output_dir=tmp_path / "reports",
        tide_stations=["C4P01"],
        buoy_stations=["COMC08"],
    )

    assert report["ready_for_surge_residual_training"] is False
    assert any("shorter than 21 days" in blocker for blocker in report["blockers"])
    assert (tmp_path / "reports" / "surge_residual_readiness_report.json").exists()
