from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch

try:
    from .config import ROOT, load_config
    from .dataset import chronological_split
    from .model import build_model, prediction_tensor
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from dataset import chronological_split
    from model import build_model, prediction_tensor


LOG = logging.getLogger(__name__)
ANCHOR_LABELS = ["H1", "H2", "H3", "H4"]
UNITS = {
    "wind_speed": "m/s",
    "wind_gust": "m/s",
    "precipitation_1hr": "mm",
    "tide_level": "cm",
    "visibility": "m",
}


GRADE_RULES: dict[str, dict[str, dict[str, tuple[float | None, float | None]]]] = {
    "tide_level": {
        "mae": {"H1": (3, 6), "H2": (5, 10), "H3": (7, 13), "H4": (10, 18)},
        "rmse": {"H1": (5, 9), "H2": (8, 14), "H3": (11, 19), "H4": (15, 25)},
    },
    "wind_speed": {
        "mae": {"H1": (0.8, 1.5), "H2": (1.2, 2.0), "H3": (1.5, 2.5), "H4": (2.0, 3.0)},
        "rmse": {"H1": (1.2, 2.2), "H2": (1.8, 2.8), "H3": (2.2, 3.5), "H4": (2.8, 4.2)},
    },
    "wind_gust": {
        "mae": {"H1": (1.0, 2.0), "H2": (1.5, 2.5), "H3": (2.0, 3.2), "H4": (2.5, 3.8)},
    },
    "precipitation_1hr": {
        "mae": {"H1": (1.0, 1.8), "H2": (1.1, 2.2), "H3": (1.1, 2.8), "H4": (1.1, 3.5)},
        "csi_threshold_1mm": {"H1": (0.50, 0.35), "H2": (0.45, 0.32), "H3": (0.40, 0.30), "H4": (0.36, 0.28)},
    },
    "visibility": {
        "mae": {"H1": (500, 1000), "H2": (700, 1400), "H3": (900, 1800), "H4": (1200, 2200)},
    },
}


def inverse_targets(values: np.ndarray, scaler_bundle: dict[str, Any], target_columns: list[str]) -> np.ndarray:
    scaler = scaler_bundle["scaler"]
    features = list(scaler_bundle["feature_columns"])
    out = np.empty_like(values, dtype=float)
    for j, col in enumerate(target_columns):
        idx = features.index(col)
        out[..., j] = (values[..., j] - scaler.min_[idx]) / scaler.scale_[idx]
    return out


def metrics_for_anchor(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    diff = y_pred - y_true
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff**2)))
    bias = float(np.mean(diff))
    nonzero = np.abs(y_true) > 1e-9
    mape = float(np.mean(np.abs(diff[nonzero] / y_true[nonzero])) * 100) if np.any(nonzero) else None
    denom = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - float(np.sum(diff**2)) / denom if denom > 0 else None
    return {"mae": mae, "rmse": rmse, "bias": bias, "mape": mape, "r2": r2}


def categorical_rain_metrics(y_true: np.ndarray, y_pred: np.ndarray, threshold: float) -> dict[str, float | int | None]:
    true_rain = y_true > threshold
    pred_rain = y_pred > threshold
    tp = int(np.sum(true_rain & pred_rain))
    fp = int(np.sum(~true_rain & pred_rain))
    fn = int(np.sum(true_rain & ~pred_rain))
    csi = tp / (tp + fp + fn) if tp + fp + fn else None
    far = fp / (tp + fp) if tp + fp else None
    pod = tp / (tp + fn) if tp + fn else None
    return {"csi": csi, "far": far, "pod": pod, "tp": tp, "fp": fp, "fn": fn}


def rain_metrics(y_true: np.ndarray, y_pred: np.ndarray, main_threshold: float = 1.0, heavy_threshold: float = 10.0) -> dict[str, float | int | None]:
    main = categorical_rain_metrics(y_true, y_pred, main_threshold)
    heavy = categorical_rain_metrics(y_true, y_pred, heavy_threshold)
    true_rain = y_true > main_threshold
    rainy = true_rain
    mae_rain = float(np.mean(np.abs(y_pred[rainy] - y_true[rainy]))) if np.any(rainy) else None
    return {
        "csi": main["csi"],
        "far": main["far"],
        "pod": main["pod"],
        "csi_threshold_1mm": main["csi"],
        "far_threshold_1mm": main["far"],
        "pod_threshold_1mm": main["pod"],
        "tp_threshold_1mm": main["tp"],
        "fp_threshold_1mm": main["fp"],
        "fn_threshold_1mm": main["fn"],
        "csi_threshold_10mm": heavy["csi"],
        "far_threshold_10mm": heavy["far"],
        "pod_threshold_10mm": heavy["pod"],
        "tp_threshold_10mm": heavy["tp"],
        "fp_threshold_10mm": heavy["fp"],
        "fn_threshold_10mm": heavy["fn"],
        "mae_rain_only": mae_rain,
    }


def grade_variable(variable: str, label: str, metrics: dict[str, float | None]) -> str:
    rules = GRADE_RULES.get(variable, {})
    grades: list[str] = []
    for metric, by_anchor in rules.items():
        value = metrics.get(metric)
        if value is None or label not in by_anchor:
            continue
        excellent, acceptable = by_anchor[label]
        if metric in {"csi", "r2"} or metric.startswith("csi_"):
            grades.append("excellent" if value >= excellent else "acceptable" if value >= acceptable else "poor")
        else:
            grades.append("excellent" if value <= excellent else "acceptable" if value <= acceptable else "poor")
    if "poor" in grades:
        return "poor"
    if "acceptable" in grades:
        return "acceptable"
    return "excellent" if grades else "acceptable"


def evaluate_model(
    station_id: str,
    target_group: str,
    config_path: str | Path = "config.yaml",
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    target_cfg = cfg.get("targets", {}).get(target_group, {})
    main_rain_threshold = float(target_cfg.get("rain_threshold_main", 1.0))
    heavy_rain_threshold = float(target_cfg.get("rain_threshold_heavy", 10.0))
    project = Path(project_root)
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_{target_group}_best.pt"
    npz_path = project / "data" / "processed" / f"{station_id}_{target_group}.npz"
    scaler_path = project / "scalers" / f"{station_id}_{target_group}_scaler.pkl"
    if not ckpt_path.exists():
        raise FileNotFoundError(ckpt_path)
    bundle = np.load(npz_path, allow_pickle=True)
    scaler_bundle = joblib.load(scaler_path)
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    model_type = checkpoint["model_type"]
    model = build_model(model_type, int(checkpoint["n_features"]), checkpoint["config"].get("model", {}))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    X = bundle["X"].astype(np.float32)
    y = bundle["y_anchors"].astype(np.float32)
    persistence = bundle["persistence"].astype(np.float32)
    _, _, test_sl = chronological_split(len(X), float(cfg["data"]["train_ratio"]), float(cfg["data"]["val_ratio"]))
    with torch.no_grad():
        x_test = torch.as_tensor(X[test_sl], dtype=torch.float32)
        if model_type == "twostage_lstm":
            raw = model(x_test)
            cls_threshold = float(target_cfg.get("inference_cls_threshold", 0.5))
            pred = torch.where(raw["probability"] > cls_threshold, raw["amount"], torch.zeros_like(raw["amount"])).cpu().numpy()
        else:
            pred = prediction_tensor(model, x_test, model_type).cpu().numpy()
    if pred.ndim == 2:
        pred = pred[..., None]
    y_test = y[test_sl]
    if y_test.ndim == 2:
        y_test = y_test[..., None]
    if persistence[test_sl].ndim == 2:
        persistence_test = persistence[test_sl][..., None]
    else:
        persistence_test = persistence[test_sl]

    target_columns = [str(x) for x in bundle["target_columns"].tolist()]
    y_orig = inverse_targets(y_test, scaler_bundle, target_columns)
    pred_orig = inverse_targets(pred, scaler_bundle, target_columns)
    pers_orig = inverse_targets(persistence_test, scaler_bundle, target_columns)

    variables: dict[str, Any] = {}
    accuracy_grade: dict[str, dict[str, str]] = {}
    beats_all = True
    for v_idx, variable in enumerate(target_columns):
        variable_report: dict[str, Any] = {}
        accuracy_grade[variable] = {}
        for a_idx, label in enumerate(ANCHOR_LABELS):
            m = metrics_for_anchor(y_orig[:, a_idx, v_idx], pred_orig[:, a_idx, v_idx])
            p = metrics_for_anchor(y_orig[:, a_idx, v_idx], pers_orig[:, a_idx, v_idx])
            if variable == "precipitation_1hr":
                m.update(rain_metrics(y_orig[:, a_idx, v_idx], pred_orig[:, a_idx, v_idx], main_rain_threshold, heavy_rain_threshold))
            beats = (m["mae"] or float("inf")) < (p["mae"] or float("inf"))
            beats_all = beats_all and beats
            m["persistence_mae"] = p["mae"]
            m["beats_persistence"] = beats
            m["unit"] = UNITS.get(variable)
            m["accuracy_grade"] = grade_variable(variable, label, m)
            accuracy_grade[variable][label] = str(m["accuracy_grade"])
            variable_report[label] = m
        variables[variable] = variable_report

    if not beats_all:
        LOG.warning("%s/%s did not beat persistence for every anchor", station_id, target_group)

    report = {
        "station_id": station_id,
        "target_group": target_group,
        "model_version": checkpoint.get("model_version", "baseline_lstm_v1"),
        "test_windows": int(len(y_orig)),
        "beats_persistence": beats_all,
        "accuracy_grade": accuracy_grade,
        "variables": variables,
    }
    out_dir = project / "results" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{station_id}_{target_group}_metrics.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_summary(out_dir / "summary_report.csv", report)
    return report


def _append_summary(path: Path, report: dict[str, Any]) -> None:
    rows = []
    for variable, anchors in report["variables"].items():
        for label, metrics in anchors.items():
            rows.append(
                {
                    "station_id": report["station_id"],
                    "target_group": report["target_group"],
                    "variable": variable,
                    "anchor": label,
                    "mae": metrics.get("mae"),
                    "rmse": metrics.get("rmse"),
                    "bias": metrics.get("bias"),
                    "accuracy_grade": metrics.get("accuracy_grade"),
                    "beats_persistence": metrics.get("beats_persistence"),
                }
            )
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    report = evaluate_model(args.station_id, args.target, args.config)
    print(json.dumps(report["accuracy_grade"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
