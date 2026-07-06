from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

try:
    from .config import ROOT, anchor_indices, full_steps, load_config, lookback_steps, target_config
    from .dataset import WindowBundle, create_windows
except ImportError:  # pragma: no cover - supports `python src/preprocess.py`
    from config import ROOT, anchor_indices, full_steps, load_config, lookback_steps, target_config
    from dataset import WindowBundle, create_windows


BASE_FEATURES = ["wind_speed", "wind_gust", "precipitation_1hr", "tide_level"]
OPTIONAL_FEATURES = ["visibility"]
CYCLIC_FEATURES = [
    "wind_dir_sin",
    "wind_dir_cos",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
    "tide_sin",
    "tide_cos",
]
LIMITS = {
    "wind_speed": (0.0, 60.0),
    "wind_gust": (0.0, 80.0),
    "precipitation_1hr": (0.0, 200.0),
    "tide_level": (-200.0, 600.0),
    "visibility": (0.0, 20000.0),
    "wind_direction": (0.0, 360.0),
}
ALIASES = {
    "wind_speed_mps": "wind_speed",
    "wind_gust_mps": "wind_gust",
    "wind_direction_deg": "wind_direction",
    "precipitation_1hr_mm": "precipitation_1hr",
    "visibility_m": "visibility",
}


def load_observations(path: str | Path) -> pd.DataFrame:
    data_path = Path(path)
    if data_path.suffix.lower() in {".parquet", ".pq"}:
        df = pd.read_parquet(data_path)
    else:
        df = pd.read_csv(data_path)
    return df.rename(columns={k: v for k, v in ALIASES.items() if k in df.columns})


def _mark_outliers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col, (lo, hi) in LIMITS.items():
        if col in out.columns:
            out.loc[(out[col] < lo) | (out[col] > hi), col] = np.nan
    return out


def _interpolate_with_limit(series: pd.Series, steps: int) -> tuple[pd.Series, pd.Series]:
    before = series.isna()
    filled = series.interpolate(method="time", limit=steps, limit_direction="both")
    invalid = before & filled.isna()
    return filled, invalid


def prepare_station_frame(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    station_id: str,
    required_variables: list[str],
) -> tuple[pd.DataFrame, pd.Series, list[dict[str, Any]]]:
    if "obs_time" not in df.columns:
        raise ValueError("Input data must include obs_time")
    if "station_id" in df.columns:
        df = df[df["station_id"].astype(str) == str(station_id)]
    if df.empty:
        raise ValueError(f"No observations found for station_id={station_id}")

    step = int(cfg["time_step_minutes"])
    work = df.copy()
    work["obs_time"] = pd.to_datetime(work["obs_time"])
    work = work.set_index("obs_time").sort_index()
    numeric_cols = [col for col in work.columns if col != "station_id"]
    work[numeric_cols] = work[numeric_cols].apply(pd.to_numeric, errors="coerce")
    work = _mark_outliers(work[numeric_cols]).resample(f"{step}min").mean()

    invalid = work.isna().all(axis=1)
    quality: list[dict[str, Any]] = []
    for col in BASE_FEATURES + OPTIONAL_FEATURES:
        if col not in work.columns:
            if col in required_variables:
                raise ValueError(f"Required variable {col!r} is missing")
            continue
        raw_valid = work[col].notna()
        participates_in_windows = col in required_variables or bool(raw_valid.any())
        if col == "precipitation_1hr":
            work[col] = work[col].fillna(0.0)
        elif col == "visibility":
            work[col] = work[col].ffill(limit=max(1, 60 // step))
        elif col == "tide_level":
            work[col], col_invalid = _interpolate_with_limit(work[col], max(1, 180 // step))
            if participates_in_windows:
                invalid = invalid | col_invalid
        else:
            work[col], col_invalid = _interpolate_with_limit(work[col], max(1, 30 // step))
            if participates_in_windows:
                invalid = invalid | col_invalid
        valid_ratio = float(raw_valid.mean()) if len(raw_valid) else 0.0
        quality.append(
            {
                "station_id": station_id,
                "variable": col,
                "valid_ratio": round(valid_ratio, 6),
                "total_steps": int(len(work)),
                "invalid_windows_excluded": 0,
            }
        )

    if "wind_direction" in work.columns and work["wind_direction"].notna().any():
        wind_dir = work["wind_direction"].ffill(limit=max(1, 60 // step)).bfill(limit=max(1, 60 // step))
        work["wind_dir_sin"] = np.sin(np.deg2rad(wind_dir))
        work["wind_dir_cos"] = np.cos(np.deg2rad(wind_dir))
    else:
        work["wind_dir_sin"] = 0.0
        work["wind_dir_cos"] = 1.0

    minutes = work.index.hour * 60 + work.index.minute
    work["hour_sin"] = np.sin(2 * np.pi * work.index.hour / 24)
    work["hour_cos"] = np.cos(2 * np.pi * work.index.hour / 24)
    work["doy_sin"] = np.sin(2 * np.pi * work.index.dayofyear / 365)
    work["doy_cos"] = np.cos(2 * np.pi * work.index.dayofyear / 365)
    work["tide_sin"] = np.sin(2 * np.pi * minutes / 745)
    work["tide_cos"] = np.cos(2 * np.pi * minutes / 745)

    work = _mark_outliers(work)
    invalid = invalid | work[required_variables].isna().any(axis=1)
    return work, invalid.fillna(True), quality


def feature_columns(frame: pd.DataFrame, include_visibility: bool = True) -> list[str]:
    cols = [col for col in BASE_FEATURES if col in frame.columns and frame[col].notna().all()]
    if include_visibility and "visibility" in frame.columns and frame["visibility"].notna().all():
        cols.append("visibility")
    cols.extend([col for col in CYCLIC_FEATURES if col in frame.columns])
    return cols


def build_window_bundle(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    station_id: str,
    target_group: str,
    output_dir: str | Path | None = None,
) -> WindowBundle:
    target = target_config(cfg, target_group)
    variables = list(target["variables"])
    frame, invalid, quality = prepare_station_frame(df, cfg, station_id, variables)
    if target.get("skip_if_missing") and any(var not in frame.columns for var in variables):
        raise ValueError(f"Skipping {target_group}: missing optional variables {variables}")

    min_valid = float(cfg.get("data", {}).get("min_valid_ratio", 0.70))
    for item in quality:
        if item["variable"] in variables and item["valid_ratio"] < min_valid:
            raise ValueError(f"{item['variable']} valid_ratio={item['valid_ratio']} below {min_valid}")

    feats = feature_columns(frame, include_visibility="visibility" in frame.columns)
    missing = [col for col in variables if col not in feats]
    if missing:
        raise ValueError(f"Target variables are not available as features: {missing}")

    numeric = frame[feats].astype(float)
    split_at = max(1, int(len(numeric) * float(cfg.get("data", {}).get("train_ratio", 0.70))))
    scaler = MinMaxScaler()
    scaled = numeric.copy()
    scaled.iloc[:split_at] = scaler.fit_transform(numeric.iloc[:split_at])
    scaled.iloc[split_at:] = scaler.transform(numeric.iloc[split_at:])

    target_indices = [feats.index(var) for var in variables]
    X, y_full, y_anchors, ts, persistence = create_windows(
        scaled.to_numpy(dtype=np.float32),
        lookback_steps(cfg),
        full_steps(cfg),
        target_indices,
        anchor_indices(cfg),
        invalid.to_numpy(dtype=bool),
        scaled.index.to_numpy(),
    )
    excluded = max(0, len(frame) - len(X))
    for item in quality:
        if item["variable"] in variables:
            item["invalid_windows_excluded"] = int(excluded)

    if output_dir is not None:
        base = Path(output_dir)
        (base / "data" / "processed").mkdir(parents=True, exist_ok=True)
        (base / "scalers").mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            base / "data" / "processed" / f"{station_id}_{target_group}.npz",
            X=X,
            y_full=y_full,
            y_anchors=y_anchors,
            timestamps=ts,
            persistence=persistence,
            feature_columns=np.asarray(feats, dtype=object),
            target_columns=np.asarray(variables, dtype=object),
            anchor_offsets_minutes=np.asarray(cfg["anchor_offsets_minutes"], dtype=int),
        )
        joblib.dump(
            {"scaler": scaler, "feature_columns": feats, "target_columns": variables},
            base / "scalers" / f"{station_id}_{target_group}_scaler.pkl",
        )
        report_path = base / "data" / "processed" / "data_quality_report.json"
        existing: list[dict[str, Any]] = []
        if report_path.exists():
            existing = json.loads(report_path.read_text(encoding="utf-8"))
        existing.extend(quality)
        report_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return WindowBundle(
        X=X,
        y_full=y_full,
        y_anchors=y_anchors,
        target_columns=variables,
        feature_columns=feats,
        anchor_offsets_minutes=list(cfg["anchor_offsets_minutes"]),
        timestamps=ts,
        persistence=persistence,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data_path", required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    df = load_observations(args.data_path)
    bundle = build_window_bundle(df, cfg, args.station_id, args.target, ROOT)
    print(f"created {len(bundle.X)} windows for {args.station_id}/{args.target}")


if __name__ == "__main__":
    main()
