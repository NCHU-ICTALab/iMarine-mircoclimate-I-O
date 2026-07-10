from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class DataAPI:
    """Internal data API for collection, preprocessing, and multi-source merging."""

    @staticmethod
    def collect_data(
        source: str,
        start_date: str,
        end_date: str,
        stations: list[str] | tuple[str, ...] | None = None,
        output_dir: str | Path | None = None,
    ) -> pd.DataFrame:
        """Load locally available records for a source/date range.

        Network collection remains source-tool specific; this method provides a stable
        internal API and reads the repository's existing raw files when available.
        """
        source = source.lower()
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        rows: list[pd.DataFrame] = []
        base = Path(output_dir) if output_dir else Path("kaohsiung_microclimate_lstm/data/raw")
        if source in {"observed_hourly", "twport", "harbor", "cwa", "codis", "all"}:
            candidates = []
            if source in {"observed_hourly", "twport", "harbor", "all"}:
                candidates.extend((base / "observed_hourly").glob("*.csv"))
            if source in {"cwa", "codis", "all"}:
                candidates.extend(base.glob("historical_weather/**/*.csv"))
            for path in candidates:
                try:
                    frame = pd.read_csv(path)
                except Exception:
                    continue
                if "station_id" not in frame.columns:
                    frame["station_id"] = path.stem.split("_")[0]
                if stations is not None and not frame["station_id"].astype(str).isin([str(s) for s in stations]).any():
                    continue
                if "obs_time" in frame.columns:
                    times = pd.to_datetime(frame["obs_time"], errors="coerce")
                    frame = frame.loc[(times >= start) & (times <= end)].copy()
                rows.append(frame)
        if not rows:
            return pd.DataFrame()
        return pd.concat(rows, ignore_index=True, sort=False)

    @staticmethod
    def preprocess_data(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
        config = config or {}
        out = df.copy()
        rename = config.get("rename", {})
        if rename:
            out = out.rename(columns=rename)
        if "obs_time" in out.columns:
            out["obs_time"] = pd.to_datetime(out["obs_time"], errors="coerce")
            out = out.dropna(subset=["obs_time"]).sort_values("obs_time")
        numeric_columns = config.get("numeric_columns")
        if numeric_columns is None:
            numeric_columns = [col for col in out.columns if col not in {"station_id", "source", "device_type", "obs_time"}]
        for col in numeric_columns:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        for col, bounds in config.get("valid_ranges", {}).items():
            if col in out.columns:
                lo, hi = bounds
                out.loc[(out[col] < lo) | (out[col] > hi), col] = pd.NA
        return out.reset_index(drop=True)

    @staticmethod
    def merge_multi_source(dfs_dict: dict[str, pd.DataFrame], how: str = "outer") -> pd.DataFrame:
        frames = []
        for source, frame in dfs_dict.items():
            item = frame.copy()
            item["source"] = item.get("source", source)
            frames.append(item)
        if not frames:
            return pd.DataFrame()
        if all("obs_time" in frame.columns and "station_id" in frame.columns for frame in frames):
            indexed = [frame.set_index(["obs_time", "station_id"]) for frame in frames]
            merged = pd.concat(indexed, axis=0 if how == "outer" else 1, join=how, sort=True)
            return merged.reset_index()
        return pd.concat(frames, ignore_index=True, sort=False)
