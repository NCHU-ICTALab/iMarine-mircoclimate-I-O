from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

try:
    from .config import ROOT, load_config
    from .evaluate import inverse_targets
    from .model import build_model, prediction_tensor
    from .preprocess import load_observations, prepare_station_frame
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from evaluate import inverse_targets
    from model import build_model, prediction_tensor
    from preprocess import load_observations, prepare_station_frame


UNITS = {
    "wind_speed": "m/s",
    "wind_gust": "m/s",
    "precipitation_1hr": "mm",
    "tide_level": "cm",
    "visibility": "m",
}
TAIPEI = timezone(timedelta(hours=8))


def _latest_grades(project: Path, station_id: str, target_group: str, target_columns: list[str]) -> dict[str, str]:
    path = project / "results" / "evaluation" / f"{station_id}_{target_group}_metrics.json"
    if not path.exists():
        return {f"H{i}": "acceptable" for i in range(1, 5)}
    report = json.loads(path.read_text(encoding="utf-8"))
    if len(target_columns) == 1:
        return report.get("accuracy_grade", {}).get(target_columns[0], {})
    merged: dict[str, str] = {}
    for label in ["H1", "H2", "H3", "H4"]:
        grades = [report.get("accuracy_grade", {}).get(col, {}).get(label, "acceptable") for col in target_columns]
        merged[label] = "poor" if "poor" in grades else "acceptable" if "acceptable" in grades else "excellent"
    return merged


def predict(
    station_id: str,
    target_group: str,
    recent_observations: pd.DataFrame,
    config_path: str = "config.yaml",
    return_uncertainty: bool = False,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    project = Path(project_root)
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_{target_group}_best.pt"
    scaler_path = project / "scalers" / f"{station_id}_{target_group}_scaler.pkl"
    if not ckpt_path.exists():
        raise FileNotFoundError(ckpt_path)
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    scaler_bundle = joblib.load(scaler_path)
    model_type = checkpoint["model_type"]
    target_columns = list(checkpoint["target_columns"])
    frame, invalid, _ = prepare_station_frame(recent_observations, cfg, station_id, target_columns)
    features = list(checkpoint["feature_columns"])
    lookback = int(float(cfg["lookback_hours"]) * 60 / int(cfg["time_step_minutes"]))
    recent = frame[features].tail(lookback)
    if len(recent) < lookback:
        raise ValueError(f"Need at least {lookback} recent rows after resampling")
    if invalid.tail(lookback).any():
        raise ValueError("Recent observations contain invalid gaps inside lookback window")

    scaler = scaler_bundle["scaler"]
    X = scaler.transform(recent.astype(float))
    model = build_model(model_type, int(checkpoint["n_features"]), checkpoint["config"].get("model", {}))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    x = torch.as_tensor(X[None, :, :], dtype=torch.float32)

    if return_uncertainty:
        model.train()
        preds = []
        with torch.no_grad():
            for _ in range(50):
                p = prediction_tensor(model, x, model_type).cpu().numpy()
                if p.ndim == 2:
                    p = p[..., None]
                preds.append(p)
        arr = np.concatenate(preds, axis=0)
        pred = arr.mean(axis=0, keepdims=True)
        std = inverse_targets(arr, scaler_bundle, target_columns).std(axis=0)
    else:
        with torch.no_grad():
            pred = prediction_tensor(model, x, model_type).cpu().numpy()
        if pred.ndim == 2:
            pred = pred[..., None]
        std = None

    pred_orig = inverse_targets(pred, scaler_bundle, target_columns)[0]
    last_time = pd.to_datetime(recent.index[-1]).to_pydatetime()
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=TAIPEI)
    grades = _latest_grades(project, station_id, target_group, target_columns)
    anchors = []
    for idx, offset in enumerate(cfg["anchor_offsets_minutes"]):
        item: dict[str, Any] = {
            "label": f"H{idx + 1}",
            "offset_minutes": int(offset),
            "timestamp": (last_time + timedelta(minutes=int(offset))).isoformat(),
        }
        for col_idx, col in enumerate(target_columns):
            value = {"value": round(float(pred_orig[idx, col_idx]), 3), "unit": UNITS.get(col)}
            if return_uncertainty and std is not None:
                value["std"] = round(float(std[idx, col_idx]), 3)
            item[col] = value
        anchors.append(item)
    return {
        "station_id": station_id,
        "target_group": target_group,
        "anchors": anchors,
        "accuracy_grade": grades,
        "model_version": checkpoint.get("model_version", "baseline_lstm_v1"),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
    }


def predict_from_file(
    station_id: str,
    target_group: str,
    data_path: str | Path,
    config_path: str = "config.yaml",
    return_uncertainty: bool = False,
) -> dict[str, Any]:
    return predict(station_id, target_group, load_observations(data_path), config_path, return_uncertainty)
