from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


pytest.importorskip("sklearn")
pytest.importorskip("yaml")

from kaohsiung_microclimate_lstm.src.config import anchor_indices, load_config
from kaohsiung_microclimate_lstm.src.preprocess import build_window_bundle


def test_anchor_indices_are_30_minute_points():
    cfg = load_config(Path("kaohsiung_microclimate_lstm") / "config.yaml")
    assert anchor_indices(cfg) == [2, 5, 8, 11]


def test_preprocess_builds_windows_and_features(tmp_path):
    start = datetime(2026, 1, 1)
    rows = []
    for i in range(120):
        rows.append(
            {
                "station_id": "KH",
                "obs_time": start + timedelta(minutes=10 * i),
                "wind_speed": 5 + np.sin(i / 8),
                "wind_gust": 7 + np.sin(i / 8),
                "wind_direction": (i * 5) % 360,
                "precipitation_1hr": 0.0,
                "tide_level": 100 + np.sin(i / 12) * 30,
                "visibility": 10000,
            }
        )
    cfg = load_config(Path("kaohsiung_microclimate_lstm") / "config.yaml")
    cfg["data"]["min_valid_ratio"] = 0.0
    bundle = build_window_bundle(pd.DataFrame(rows), cfg, "KH", "tide_level", tmp_path)
    assert bundle.X.shape[1] == 72
    assert bundle.y_anchors.shape[1] == 4
    assert "tide_sin" in bundle.feature_columns
    assert (tmp_path / "data" / "processed" / "data_quality_report.json").exists()
