from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from ..risk.level_mapping import map_wind_gust_to_level, map_wind_speed_to_level
except ImportError:  # pragma: no cover
    from risk.level_mapping import map_wind_gust_to_level, map_wind_speed_to_level


def build_dispatch_labels(observations: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    frame = observations.copy()
    offsets = list(config.get("anchor_offsets_minutes", [30, 60, 90, 120]))
    step = int(config.get("time_step_minutes", 10))
    rain_threshold = float(config.get("rain_probability", {}).get("threshold_mm", 0.0))
    for index, offset in enumerate(offsets, start=1):
        shift = max(1, int(offset / step))
        if "precipitation_1hr" in frame:
            frame[f"rain_event_H{index}"] = (frame["precipitation_1hr"].shift(-shift) > rain_threshold).astype("Int64")
        if "wind_speed" in frame:
            speed = frame["wind_speed"].shift(-shift)
            frame[f"future_wind_speed_mps_H{index}"] = speed
            frame[f"future_wind_level_H{index}"] = speed.map(lambda value: map_wind_speed_to_level(value, config) if pd.notna(value) else None)
        if "wind_gust" in frame:
            gust = frame["wind_gust"].shift(-shift)
            frame[f"future_wind_gust_mps_H{index}"] = gust
            frame[f"future_gust_level_H{index}"] = gust.map(lambda value: map_wind_gust_to_level(value, config) if pd.notna(value) else None)
    return frame
