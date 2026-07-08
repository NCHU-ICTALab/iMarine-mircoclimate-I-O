from __future__ import annotations

import argparse
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STATION_LAT = {"C4P01": 22.62, "1786": 22.84, "C4Q01": 22.34, "C4Q02": 22.47}
CONSTITUENT_PERIOD_HOURS = {
    "M2": 12.4206,
    "S2": 12.0,
    "N2": 12.6583,
    "K1": 23.9345,
    "O1": 25.8193,
    "P1": 24.0659,
}


@dataclass
class FallbackHarmonic:
    origin: pd.Timestamp
    periods: dict[str, float]
    beta: np.ndarray


def fit_harmonic(station_id: str, obs_df: pd.DataFrame, project_root: str | Path = "kaohsiung_microclimate_lstm") -> dict[str, Any]:
    df = obs_df.copy()
    df["obs_time"] = pd.to_datetime(df["obs_time"])
    df = df.dropna(subset=["obs_time", "tide_level"]).sort_values("obs_time")
    if len(df) < 24:
        raise ValueError(f"Need at least 24 tide observations for harmonic fit: {station_id}")
    project = Path(project_root)
    path = project / "models" / "tide" / f"{station_id}_harmonic_coef.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import utide

        coef = utide.solve(
            _to_matlab_datenum(df["obs_time"]),
            df["tide_level"].astype(float).to_numpy(),
            lat=STATION_LAT.get(station_id, 22.6),
            method="ols",
            conf_int="linear",
            verbose=False,
        )
        payload = {"kind": "utide", "station_id": station_id, "coef": coef}
        constituent_count = len(coef.name)
        main = list(coef.name[:5])
    except Exception:
        model = _fit_fallback(df["obs_time"], df["tide_level"].astype(float).to_numpy())
        payload = {"kind": "fallback_least_squares", "station_id": station_id, "model": model}
        constituent_count = len(model.periods)
        main = list(model.periods)

    with path.open("wb") as fh:
        pickle.dump(payload, fh)
    return {"station_id": station_id, "path": str(path), "kind": payload["kind"], "constituent_count": constituent_count, "main_constituents": main}


def predict_harmonic(station_id: str, future_times: pd.DatetimeIndex, project_root: str | Path = "kaohsiung_microclimate_lstm") -> pd.Series:
    path = Path(project_root) / "models" / "tide" / f"{station_id}_harmonic_coef.pkl"
    with path.open("rb") as fh:
        payload = pickle.load(fh)
    times = pd.to_datetime(future_times)
    if payload["kind"] == "utide":
        import utide

        tide = utide.reconstruct(_to_matlab_datenum(times), payload["coef"], verbose=False)
        values = tide.h
    else:
        values = _predict_fallback(payload["model"], times)
    return pd.Series(values, index=times, name="tide_level_pred")


def evaluate_tide_harmonic(station_id: str, obs_df: pd.DataFrame, project_root: str | Path = "kaohsiung_microclimate_lstm") -> dict[str, Any]:
    df = obs_df.copy()
    df["obs_time"] = pd.to_datetime(df["obs_time"])
    df = df.dropna(subset=["obs_time", "tide_level"]).sort_values("obs_time")
    if len(df) < 6:
        raise ValueError("Need at least 6 rows for harmonic evaluation")
    split = max(1, int(len(df) * 0.85))
    train_df = df.iloc[:split]
    test_df = df.iloc[split:]
    fit_info = fit_harmonic(station_id, train_df, project_root)
    pred = predict_harmonic(station_id, pd.DatetimeIndex(test_df["obs_time"]), project_root)
    true = test_df["tide_level"].astype(float).to_numpy()
    yhat = pred.to_numpy(dtype=float)
    diff = yhat - true
    denom = float(np.sum((true - np.mean(true)) ** 2))
    report = {
        "station_id": station_id,
        "model_type": "harmonic",
        "fit": fit_info,
        "test_rows": int(len(test_df)),
        "MAE_cm": float(np.mean(np.abs(diff))),
        "RMSE_cm": float(np.sqrt(np.mean(diff**2))),
        "Bias_cm": float(np.mean(diff)),
        "R2": 1.0 - float(np.sum(diff**2)) / denom if denom > 0 else None,
    }
    out = Path(project_root) / "results" / "evaluation" / f"{station_id}_tide_harmonic_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _fit_fallback(times: pd.Series, values: np.ndarray) -> FallbackHarmonic:
    ts = pd.to_datetime(times)
    origin = ts.iloc[0] if hasattr(ts, "iloc") else ts[0]
    hours = ((ts - origin) / pd.Timedelta(hours=1)).to_numpy(dtype=float)
    X = _design_matrix(hours)
    beta, *_ = np.linalg.lstsq(X, values, rcond=None)
    return FallbackHarmonic(pd.Timestamp(origin), dict(CONSTITUENT_PERIOD_HOURS), beta)


def _predict_fallback(model: FallbackHarmonic, times: pd.DatetimeIndex) -> np.ndarray:
    hours = ((pd.to_datetime(times) - model.origin) / pd.Timedelta(hours=1)).to_numpy(dtype=float)
    return _design_matrix(hours, model.periods).dot(model.beta)


def _design_matrix(hours: np.ndarray, periods: dict[str, float] | None = None) -> np.ndarray:
    periods = periods or CONSTITUENT_PERIOD_HOURS
    cols = [np.ones_like(hours)]
    for period in periods.values():
        angle = 2 * np.pi * hours / period
        cols.extend([np.sin(angle), np.cos(angle)])
    return np.column_stack(cols)


def _to_matlab_datenum(times: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    ts = pd.to_datetime(times)
    return np.array([t.to_pydatetime().toordinal() + 366 + (t.hour + t.minute / 60 + t.second / 3600) / 24 for t in ts])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--data_path", required=True)
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    args = parser.parse_args()
    df = pd.read_csv(args.data_path)
    print(json.dumps(evaluate_tide_harmonic(args.station_id, df, args.project_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
