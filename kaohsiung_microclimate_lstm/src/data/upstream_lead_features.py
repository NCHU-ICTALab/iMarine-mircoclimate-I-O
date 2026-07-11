from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


DEFAULT_SEASON_MONTH_RULES = {
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "autumn": [9, 10, 11],
    "winter": [12, 1, 2],
    "typhoon": [],
}


def load_zoning_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    zoning_path = Path(path)
    if not zoning_path.is_absolute() and not zoning_path.exists():
        zoning_path = Path(__file__).resolve().parents[2] / zoning_path
    if not zoning_path.exists():
        return {}
    return yaml.safe_load(zoning_path.read_text(encoding="utf-8")) or {}


def resolve_season(timestamp: Any, zoning: dict[str, Any]) -> str | None:
    time = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(time):
        return None
    month = int(time.month)
    typhoon_months = [int(value) for value in (zoning.get("typhoon_season_months") or [])]
    if month in typhoon_months:
        return "typhoon"
    rules = zoning.get("season_month_ranges") or zoning.get("season_month_rules") or DEFAULT_SEASON_MONTH_RULES
    for season, months in rules.items():
        if month in [int(value) for value in (months or [])]:
            return str(season)
    return None


def build_upstream_lead_features(raw: pd.DataFrame, zoning: dict[str, Any], selected_station_ids: list[str]) -> pd.DataFrame:
    if raw.empty or "obs_time" not in raw.columns or "station_id" not in raw.columns:
        return pd.DataFrame(columns=["obs_time", *_feature_columns()])
    selected = {str(station_id) for station_id in selected_station_ids}
    upstream_by_season = _upstream_station_map(zoning)
    work = raw.copy()
    work["obs_time"] = pd.to_datetime(work["obs_time"], errors="coerce")
    work = work.dropna(subset=["obs_time"]).copy()
    work["station_id"] = work["station_id"].astype(str)
    rows = []
    for obs_time, group in work.groupby("obs_time", sort=True):
        season = resolve_season(obs_time, zoning)
        upstream_ids = set(upstream_by_season.get(str(season), [])) & selected
        subset = group[group["station_id"].isin(upstream_ids)] if upstream_ids else group.iloc[0:0]
        row: dict[str, Any] = {
            "obs_time": obs_time,
            "upstream_subset_season_code": _season_code(season),
            "upstream_subset_station_count": int(subset["station_id"].nunique()) if not subset.empty else 0,
        }
        for source, prefix in [
            ("wind_speed", "upstream_subset_wind_speed"),
            ("wind_gust", "upstream_subset_wind_gust"),
            ("precipitation_1hr", "upstream_subset_precipitation_1hr"),
        ]:
            values = pd.to_numeric(subset[source], errors="coerce") if source in subset.columns else pd.Series(dtype=float)
            row[f"{prefix}_mean"] = float(values.mean()) if values.notna().any() else np.nan
            row[f"{prefix}_max"] = float(values.max()) if values.notna().any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _upstream_station_map(zoning: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for pair in zoning.get("upstream_downstream_pairs", []) or []:
        season = str(pair.get("season", ""))
        station_ids = [str(station_id) for station_id in pair.get("upstream_station_ids", []) or []]
        mapping.setdefault(season, [])
        for station_id in station_ids:
            if station_id not in mapping[season]:
                mapping[season].append(station_id)
    return mapping


def _season_code(season: str | None) -> float:
    codes = {"spring": 1.0, "summer": 2.0, "autumn": 3.0, "winter": 4.0, "typhoon": 5.0}
    return codes.get(str(season), np.nan)


def _feature_columns() -> list[str]:
    return [
        "upstream_subset_season_code",
        "upstream_subset_station_count",
        "upstream_subset_wind_speed_mean",
        "upstream_subset_wind_speed_max",
        "upstream_subset_wind_gust_mean",
        "upstream_subset_wind_gust_max",
        "upstream_subset_precipitation_1hr_mean",
        "upstream_subset_precipitation_1hr_max",
    ]
