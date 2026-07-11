from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


COLUMN_MAPPING = {
    "WS": "wind_speed",
    "WD": "wind_direction",
    "WSGust": "wind_gust",
    "WDGust": "wind_gust_direction",
    "Precp": "precipitation_1hr",
    "PrecpHour": "precipitation_1hr",
    "RH": "relative_humidity",
    "Tx": "temperature",
    "Td": "dew_point",
    "StnPres": "station_pressure",
    "SeaPres": "sea_level_pressure",
    "Visb": "visibility",
    "觀測時間(hour)": "obs_time",
    "測站氣壓(hPa)": "station_pressure",
    "氣溫(℃)": "temperature",
    "相對溼度(%)": "relative_humidity",
    "風速(m/s)": "wind_speed",
    "風向(360degree)": "wind_direction",
    "最大陣風(m/s)": "wind_gust",
    "最大陣風風向(360degree)": "wind_gust_direction",
    "降水量(mm)": "precipitation_1hr",
}

PHYSICAL_RANGE_LIMITS = {
    "wind_speed": (0.0, 100.0),
    "wind_gust": (0.0, 120.0),
    "precipitation_1hr": (0.0, 500.0),
    "relative_humidity": (0.0, 100.0),
    "station_pressure": (800.0, 1100.0),
    "sea_level_pressure": (800.0, 1100.0),
    "temperature": (-20.0, 50.0),
    "visibility": (0.0, 100000.0),
    "dew_point": (-30.0, 40.0),
}


def normalize_historical_weather_frame(frame: pd.DataFrame, station_id: str) -> pd.DataFrame:
    work = frame.copy()
    work.columns = [str(col).replace("\ufeff", "").strip() for col in work.columns]
    work = work.rename(columns={key: value for key, value in COLUMN_MAPPING.items() if key in work.columns})
    time_col = _resolve_time_column(work)
    if time_col is None:
        raise ValueError("historical weather frame has no recognizable time column")
    work["obs_time"] = pd.to_datetime(work[time_col], errors="coerce")
    work = work.dropna(subset=["obs_time"]).copy()
    work["station_id"] = str(station_id)
    for column in [
        "wind_speed",
        "wind_direction",
        "wind_gust",
        "wind_gust_direction",
        "precipitation_1hr",
        "relative_humidity",
        "temperature",
        "dew_point",
        "station_pressure",
        "sea_level_pressure",
        "visibility",
    ]:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
            if column in PHYSICAL_RANGE_LIMITS:
                low, high = PHYSICAL_RANGE_LIMITS[column]
                work.loc[~work[column].between(low, high), column] = pd.NA
    keep = ["obs_time", "station_id", *[col for col in COLUMN_MAPPING.values() if col in work.columns]]
    return work.loc[:, list(dict.fromkeys(keep))].sort_values("obs_time").reset_index(drop=True)


def load_historical_weather_csv(path: str | Path, station_id: str | None = None) -> pd.DataFrame:
    csv_path = Path(path)
    sid = station_id or csv_path.stem.split("_")[0]
    last_error: Exception | None = None
    for encoding in ["utf-8-sig", "utf-8", "big5", "cp950"]:
        try:
            frame = pd.read_csv(csv_path, encoding=encoding)
            return normalize_historical_weather_frame(frame, sid)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Unable to read historical weather CSV: {csv_path}") from last_error


def write_normalized_parquet(frame: pd.DataFrame, output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
        return "parquet"
    except Exception:
        frame.to_pickle(path)
        return "pickle"


def _resolve_time_column(frame: pd.DataFrame) -> str | None:
    candidates = ["obs_time", "timestamp", "Datetime", "DateTime", "ObsTime", "ObsTimeDate", "DataTime", "time", "date"]
    for column in candidates:
        if column in frame.columns:
            return column
    if {"Date", "Time"}.issubset(frame.columns):
        frame["obs_time"] = frame["Date"].astype(str) + " " + frame["Time"].astype(str)
        return "obs_time"
    return None
