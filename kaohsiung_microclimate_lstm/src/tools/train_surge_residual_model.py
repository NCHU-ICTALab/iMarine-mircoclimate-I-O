from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from ..tide.harmonic_model import fit_harmonic, predict_harmonic
except ImportError:  # pragma: no cover
    from tide.harmonic_model import fit_harmonic, predict_harmonic


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_TARGET_STATIONS = ["C4P01"]
DEFAULT_FEATURE_STATIONS = ["C4Q01", "C4Q02", "COMC08", "46714D"]
FEATURE_COLUMNS = ["air_pressure", "wind_speed", "wind_gust", "wind_direction", "wave_height", "wave_period"]


def train_surge_residual_model(
    observed_dir: str | Path = "kaohsiung_microclimate_lstm/data/raw/observed_hourly",
    output_dir: str | Path = "kaohsiung_microclimate_lstm/models/tide_surge_v13",
    report_dir: str | Path = "kaohsiung_microclimate_lstm/results/tide_surge_v13",
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    target_stations: list[str] | None = None,
    feature_stations: list[str] | None = None,
    min_rows: int = 336,
) -> dict[str, Any]:
    observed = Path(observed_dir)
    output = Path(output_dir)
    reports = Path(report_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    targets = target_stations or DEFAULT_TARGET_STATIONS
    features = feature_stations or DEFAULT_FEATURE_STATIONS
    station_frames = {station_id: _load_station_frame(observed / f"{station_id}.csv") for station_id in sorted(set(targets + features))}
    station_reports = {}
    trained_models = {}
    blockers = []
    for target_station in targets:
        target_frame = station_frames.get(target_station, pd.DataFrame())
        if target_frame.empty:
            blockers.append(f"{target_station} observation file missing or empty")
            continue
        dataset = _build_surge_dataset(target_station, target_frame, {sid: station_frames.get(sid, pd.DataFrame()) for sid in features})
        if len(dataset) < int(min_rows):
            blockers.append(f"{target_station} has only {len(dataset)} aligned rows; need {min_rows}")
            continue
        trained = _train_one_station(target_station, dataset, output, project_root)
        trained_models[target_station] = trained
        station_reports[target_station] = _station_data_report(dataset, features)

    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "model_family": "surge_residual_model",
        "trained": bool(trained_models) and not blockers,
        "target_stations": targets,
        "feature_stations": features,
        "min_required_rows": int(min_rows),
        "trained_models": trained_models,
        "station_reports": station_reports,
        "blockers": blockers,
        "method": "observed_tide_minus_harmonic_tide_residual_random_forest",
    }
    (reports / "surge_residual_training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_station_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "obs_time" not in frame.columns:
        return pd.DataFrame()
    frame["obs_time"] = pd.to_datetime(frame["obs_time"], errors="coerce")
    frame = frame.dropna(subset=["obs_time"]).sort_values("obs_time")
    return frame


def _build_surge_dataset(target_station: str, target_frame: pd.DataFrame, feature_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    target = target_frame[["obs_time", "tide_level"]].copy()
    target["tide_level"] = pd.to_numeric(target["tide_level"], errors="coerce")
    target = target.dropna(subset=["tide_level"])
    dataset = target
    for station_id, frame in feature_frames.items():
        if frame.empty:
            continue
        cols = ["obs_time", *[col for col in FEATURE_COLUMNS if col in frame.columns]]
        part = frame[cols].copy()
        rename = {col: f"{station_id}_{col}" for col in cols if col != "obs_time"}
        part = part.rename(columns=rename)
        for col in rename.values():
            part[col] = pd.to_numeric(part[col], errors="coerce")
        dataset = dataset.merge(part, on="obs_time", how="left")
    dataset = _add_time_features(dataset)
    dataset["target_station_id"] = target_station
    return dataset.sort_values("obs_time").reset_index(drop=True)


def _add_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    times = pd.to_datetime(out["obs_time"], errors="coerce")
    hour = times.dt.hour + times.dt.minute / 60.0
    doy = times.dt.dayofyear
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 366.0)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 366.0)
    return out


def _train_one_station(target_station: str, dataset: pd.DataFrame, output_dir: Path, project_root: str | Path) -> dict[str, Any]:
    split = max(1, int(len(dataset) * 0.8))
    train = dataset.iloc[:split].copy()
    test = dataset.iloc[split:].copy()
    harmonic_fit = fit_harmonic(target_station, train[["obs_time", "tide_level"]], project_root)
    train_harmonic = predict_harmonic(target_station, pd.DatetimeIndex(train["obs_time"]), project_root).to_numpy(dtype=float)
    test_harmonic = predict_harmonic(target_station, pd.DatetimeIndex(test["obs_time"]), project_root).to_numpy(dtype=float)
    train["surge_residual"] = train["tide_level"].to_numpy(dtype=float) - train_harmonic
    test["surge_residual"] = test["tide_level"].to_numpy(dtype=float) - test_harmonic
    feature_columns = [col for col in dataset.columns if col not in {"obs_time", "tide_level", "target_station_id"}]
    fill = train[feature_columns].median(numeric_only=True)
    x_train = train[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    y_train = train["surge_residual"].astype(float)
    model = RandomForestRegressor(n_estimators=120, random_state=42, min_samples_leaf=2)
    model.fit(x_train, y_train)
    x_test = test[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(fill).fillna(0.0)
    residual_pred = model.predict(x_test)
    tide_pred = test_harmonic + residual_pred
    residual_true = test["surge_residual"].to_numpy(dtype=float)
    tide_true = test["tide_level"].to_numpy(dtype=float)
    model_path = output_dir / f"{target_station}_surge_residual.joblib"
    joblib.dump(
        {
            "model": model,
            "target_station_id": target_station,
            "feature_columns": feature_columns,
            "fill_values": fill.to_dict(),
            "harmonic_model": harmonic_fit,
            "label_column": "surge_residual",
            "algorithm": "random_forest",
        },
        model_path,
    )
    return {
        "model_path": str(model_path),
        "harmonic_model_path": harmonic_fit.get("path"),
        "rows": int(len(dataset)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "feature_columns": feature_columns,
        "metrics": {
            "surge_residual_MAE": round(float(mean_absolute_error(residual_true, residual_pred)), 4),
            "surge_residual_RMSE": round(float(np.sqrt(mean_squared_error(residual_true, residual_pred))), 4),
            "surge_residual_R2": round(float(r2_score(residual_true, residual_pred)), 4) if len(test) > 1 else None,
            "tide_level_MAE": round(float(mean_absolute_error(tide_true, tide_pred)), 4),
            "tide_level_RMSE": round(float(np.sqrt(mean_squared_error(tide_true, tide_pred))), 4),
            "tide_level_R2": round(float(r2_score(tide_true, tide_pred)), 4) if len(test) > 1 else None,
        },
    }


def _station_data_report(dataset: pd.DataFrame, feature_stations: list[str]) -> dict[str, Any]:
    report = {"aligned_rows": int(len(dataset)), "feature_non_null": {}}
    for station_id in feature_stations:
        report["feature_non_null"][station_id] = {
            col: int(dataset.get(f"{station_id}_{col}", pd.Series(dtype=float)).notna().sum())
            for col in FEATURE_COLUMNS
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-dir", default="kaohsiung_microclimate_lstm/data/raw/observed_hourly")
    parser.add_argument("--output-dir", default="kaohsiung_microclimate_lstm/models/tide_surge_v13")
    parser.add_argument("--report-dir", default="kaohsiung_microclimate_lstm/results/tide_surge_v13")
    parser.add_argument("--project-root", default="kaohsiung_microclimate_lstm")
    parser.add_argument("--target-stations", default="C4P01")
    parser.add_argument("--feature-stations", default="C4Q01,C4Q02,COMC08,46714D")
    parser.add_argument("--min-rows", type=int, default=336)
    args = parser.parse_args()
    report = train_surge_residual_model(
        args.observed_dir,
        args.output_dir,
        args.report_dir,
        args.project_root,
        [item.strip() for item in args.target_stations.split(",") if item.strip()],
        [item.strip() for item in args.feature_stations.split(",") if item.strip()],
        args.min_rows,
    )
    print(json.dumps({"trained": report["trained"], "blockers": report["blockers"], "trained_models": report["trained_models"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
