from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from ..config import ROOT, load_config
    from ..dataset import chronological_split
    from ..evaluate import ANCHOR_LABELS, categorical_rain_metrics, inverse_targets
    from ..model import build_model
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from dataset import chronological_split
    from evaluate import ANCHOR_LABELS, categorical_rain_metrics, inverse_targets
    from model import build_model


THRESHOLDS = np.arange(0.25, 0.86, 0.05)


def sweep_thresholds(
    station_id: str,
    config_path: str | Path = "kaohsiung_microclimate_lstm/config_hourly_codis.yaml",
    project_root: str | Path = ROOT,
    target_group: str = "precipitation",
) -> dict[str, Any]:
    cfg = load_config(config_path)
    target_cfg = cfg["targets"][target_group]
    project = Path(project_root)
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_{target_group}_best.pt"
    npz_path = project / "data" / "processed" / f"{station_id}_{target_group}.npz"
    scaler_path = project / "scalers" / f"{station_id}_{target_group}_scaler.pkl"
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    bundle = np.load(npz_path, allow_pickle=True)
    scaler_bundle = joblib.load(scaler_path)
    model = build_model(checkpoint["model_type"], int(checkpoint["n_features"]), checkpoint["config"].get("model", {}))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    X = bundle["X"].astype(np.float32)
    y = bundle["y_anchors"].astype(np.float32)
    _, _, test_sl = chronological_split(len(X), float(cfg["data"]["train_ratio"]), float(cfg["data"]["val_ratio"]))
    with torch.no_grad():
        raw = model(torch.as_tensor(X[test_sl], dtype=torch.float32))
    prob = raw["probability"].cpu().numpy()
    amount_scaled = raw["amount"].cpu().numpy()
    if y[test_sl].ndim == 2:
        y_test = y[test_sl][..., None]
    else:
        y_test = y[test_sl]
    target_columns = [str(x) for x in bundle["target_columns"].tolist()]
    y_orig = inverse_targets(y_test, scaler_bundle, target_columns)[..., 0]
    amount_orig = inverse_targets(amount_scaled[..., None], scaler_bundle, target_columns)[..., 0]

    rows = []
    rain_threshold = float(target_cfg.get("rain_threshold_main", 1.0))
    for threshold in THRESHOLDS:
        pred_orig = np.where(prob > threshold, amount_orig, 0.0)
        anchor_metrics = []
        for idx, label in enumerate(ANCHOR_LABELS):
            metric = categorical_rain_metrics(y_orig[:, idx], pred_orig[:, idx], rain_threshold)
            anchor_metrics.append(metric)
            rows.append(
                {
                    "threshold": round(float(threshold), 2),
                    "anchor": label,
                    "csi": metric["csi"],
                    "far": metric["far"],
                    "pod": metric["pod"],
                    "tp": metric["tp"],
                    "fp": metric["fp"],
                    "fn": metric["fn"],
                }
            )
        valid_values = [m for m in anchor_metrics if m["csi"] is not None]
        rows.append(
            {
                "threshold": round(float(threshold), 2),
                "anchor": "mean",
                "csi": float(np.mean([m["csi"] for m in valid_values])) if valid_values else None,
                "far": float(np.mean([m["far"] for m in valid_values if m["far"] is not None])) if valid_values else None,
                "pod": float(np.mean([m["pod"] for m in valid_values if m["pod"] is not None])) if valid_values else None,
                "tp": sum(int(m["tp"]) for m in anchor_metrics),
                "fp": sum(int(m["fp"]) for m in anchor_metrics),
                "fn": sum(int(m["fn"]) for m in anchor_metrics),
            }
        )

    out_dir = project / "results"
    plot_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = out_dir / f"threshold_sweep_{station_id}_{target_group}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    mean_df = df[df["anchor"] == "mean"].copy()
    valid = mean_df[mean_df["far"].fillna(1.0) < 0.55]
    best = valid.loc[valid["csi"].idxmax()] if not valid.empty else mean_df.loc[mean_df["csi"].idxmax()]

    plt.figure(figsize=(8, 5))
    plt.plot(mean_df["threshold"], mean_df["csi"], "b-o", label="CSI")
    plt.plot(mean_df["threshold"], mean_df["far"], "r-s", label="FAR")
    plt.axvline(float(best["threshold"]), color="green", linestyle="--", label=f"Best={best['threshold']}")
    plt.xlabel("Inference threshold")
    plt.ylabel("Score")
    plt.title(f"{station_id} precipitation threshold sweep")
    plt.legend()
    plt.tight_layout()
    plot_path = plot_dir / f"threshold_sweep_{station_id}_{target_group}.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()

    report = {
        "station_id": station_id,
        "target_group": target_group,
        "best_threshold": float(best["threshold"]),
        "best_csi_mean": None if pd.isna(best["csi"]) else float(best["csi"]),
        "best_far_mean": None if pd.isna(best["far"]) else float(best["far"]),
        "csv_path": str(csv_path),
        "plot_path": str(plot_path),
    }
    (out_dir / f"threshold_sweep_{station_id}_{target_group}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--target", default="precipitation")
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config_hourly_codis.yaml")
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    args = parser.parse_args()
    print(json.dumps(sweep_thresholds(args.station_id, args.config, args.project_root, args.target), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
