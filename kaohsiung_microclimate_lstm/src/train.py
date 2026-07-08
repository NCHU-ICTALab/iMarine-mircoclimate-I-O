from __future__ import annotations

import argparse
import csv
import json
import logging
import random
from pathlib import Path
from typing import Any

import numpy as np
import joblib
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

try:
    from .config import ROOT, load_config, target_config
    from .dataset import LSTMDataset, build_precipitation_sampler, chronological_split
    from .model import build_model, precipitation_loss
    from .preprocess import build_window_bundle, load_observations
except ImportError:  # pragma: no cover
    from config import ROOT, load_config, target_config
    from dataset import LSTMDataset, build_precipitation_sampler, chronological_split
    from model import build_model, precipitation_loss
    from preprocess import build_window_bundle, load_observations


LOG = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def compute_loss(model_type: str, output: Any, y: Any, loss_cfg: dict[str, Any] | None = None) -> torch.Tensor:
    mse = nn.MSELoss()
    if model_type == "twostage_lstm":
        loss_cfg = loss_cfg or {}
        if loss_cfg.get("type", "focal_bce_plus_mse") == "focal_bce_plus_mse":
            return precipitation_loss(
                output,
                y,
                alpha=float(loss_cfg.get("focal_alpha", 0.75)),
                gamma=float(loss_cfg.get("focal_gamma", 2.0)),
                lambda_reg=float(loss_cfg.get("lambda_reg", 0.5)),
            )
        bce = nn.BCEWithLogitsLoss()
        return bce(output["logits"], y["binary"]) + float(loss_cfg.get("lambda_reg", 0.5)) * mse(output["amount"], y["amount"])
    return mse(output, y)


def move_target(y: Any, device: torch.device) -> Any:
    if isinstance(y, dict):
        return {key: value.to(device) for key, value in y.items()}
    return y.to(device)


def train_model(
    station_id: str,
    target_group: str,
    data_path: str | Path,
    config_path: str | Path = "config.yaml",
    project_root: str | Path = ROOT,
) -> Path:
    cfg = load_config(config_path)
    set_seed(int(cfg.get("training", {}).get("random_seed", 42)))
    target = target_config(cfg, target_group)
    model_type = target["model_type"]
    df = load_observations(data_path)
    bundle = build_window_bundle(df, cfg, station_id, target_group, project_root)
    if len(bundle.X) < 3:
        raise ValueError("Not enough valid windows after preprocessing")

    train_sl, val_sl, _ = chronological_split(
        len(bundle.X),
        float(cfg["data"]["train_ratio"]),
        float(cfg["data"]["val_ratio"]),
    )
    batch_size = int(cfg["training"].get("batch_size", 64))
    rain_threshold = scaled_rain_threshold(project_root, station_id, target_group, target) if model_type == "twostage_lstm" else 0.1
    train_ds = LSTMDataset(bundle.X[train_sl], bundle.y_anchors[train_sl], model_type, rain_threshold=rain_threshold)
    val_ds = LSTMDataset(bundle.X[val_sl], bundle.y_anchors[val_sl], model_type, rain_threshold=rain_threshold)
    if model_type == "twostage_lstm" and bool(target.get("use_weighted_sampler", False)):
        train_loader = DataLoader(train_ds, batch_size=batch_size, sampler=build_precipitation_sampler(train_ds))
    else:
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    loss_cfg = target.get("loss", {}) if isinstance(target.get("loss", {}), dict) else {}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(model_type, bundle.X.shape[-1], cfg.get("model", {})).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(cfg["training"].get("learning_rate", 1e-3)))
    lr_cfg = cfg["training"].get("lr_scheduler", {})
    if not isinstance(lr_cfg, dict):
        lr_cfg = {}
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        patience=int(lr_cfg.get("patience", cfg["training"].get("lr_scheduler_patience", 7))),
        factor=float(lr_cfg.get("factor", cfg["training"].get("lr_scheduler_factor", 0.5))),
        min_lr=float(lr_cfg.get("min_lr", 0.0)),
    )
    max_epochs = int(cfg["training"].get("max_epochs", 150))
    patience = int(cfg["training"].get("early_stopping_patience", 15))
    min_delta = float(cfg["training"].get("early_stopping_min_delta", 0.0))
    clip = float(cfg["training"].get("gradient_clip", 1.0))
    best_val = float("inf")
    stale = 0
    ckpt_dir = Path(project_root) / "models" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / f"{station_id}_{target_group}_best.pt"
    log_dir = Path(project_root) / "logs" / "training"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_rows: list[dict[str, float | int]] = []

    for epoch in tqdm(range(1, max_epochs + 1), desc=f"{station_id}/{target_group}"):
        model.train()
        train_losses = []
        for X, y in train_loader:
            X = X.to(device)
            y = move_target(y, device)
            optimizer.zero_grad(set_to_none=True)
            loss = compute_loss(model_type, model(X), y, loss_cfg)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), clip)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))

        model.eval()
        val_losses = []
        with torch.no_grad():
            for X, y in val_loader:
                X = X.to(device)
                y = move_target(y, device)
                val_losses.append(float(compute_loss(model_type, model(X), y, loss_cfg).detach().cpu()))
        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        scheduler.step(val_loss)
        lr = float(optimizer.param_groups[0]["lr"])
        log_rows.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss, "lr": lr})
        if val_loss < best_val - min_delta:
            best_val = val_loss
            stale = 0
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "station_id": station_id,
                    "target_group": target_group,
                    "model_type": model_type,
                    "n_features": int(bundle.X.shape[-1]),
                    "feature_columns": bundle.feature_columns,
                    "target_columns": bundle.target_columns,
                    "anchor_offsets_minutes": bundle.anchor_offsets_minutes,
                    "config": cfg,
                    "model_version": "baseline_lstm_v2.3_pure_temporal" if target_group == "precipitation" else "baseline_lstm_v2",
                    "best_val_loss": best_val,
                    "rain_threshold_scaled": rain_threshold if model_type == "twostage_lstm" else None,
                },
                ckpt_path,
            )
        else:
            stale += 1
            if stale >= patience:
                break

    (log_dir / f"{station_id}_{target_group}.json").write_text(json.dumps(log_rows, indent=2), encoding="utf-8")
    csv_path = log_dir / f"{station_id}_{target_group}_loss.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["epoch", "train_loss", "val_loss", "lr"])
        writer.writeheader()
        writer.writerows(log_rows)

    diagnose_training(log_rows, patience)
    try:
        from .plot_training import plot_loss
    except ImportError:  # pragma: no cover
        from plot_training import plot_loss

    try:
        plot_loss(csv_path, Path(project_root) / "results" / "plots" / f"{station_id}_{target_group}_loss.png")
    except Exception as exc:  # plotting should not invalidate training
        LOG.warning("Unable to plot loss for %s/%s: %s", station_id, target_group, exc)
    try:
        from .evaluate import evaluate_model
    except ImportError:  # pragma: no cover
        from evaluate import evaluate_model

    evaluate_model(station_id, target_group, config_path, project_root)
    return ckpt_path


def scaled_rain_threshold(project_root: str | Path, station_id: str, target_group: str, target: dict[str, Any]) -> float:
    threshold_mm = float(target.get("rain_threshold_main", 1.0))
    scaler_path = Path(project_root) / "scalers" / f"{station_id}_{target_group}_scaler.pkl"
    scaler_bundle = joblib.load(scaler_path)
    features = list(scaler_bundle["feature_columns"])
    idx = features.index("precipitation_1hr")
    scaler = scaler_bundle["scaler"]
    return float(threshold_mm * scaler.scale_[idx] + scaler.min_[idx])


def diagnose_training(log_rows: list[dict[str, float | int]], patience: int) -> None:
    if not log_rows:
        return
    first = log_rows[0]
    last = log_rows[-1]
    stopped_early = len(log_rows) <= max(5, patience // 2)
    if stopped_early:
        LOG.warning("Training stopped very early; if loss is unstable, reduce learning_rate and rerun.")
    if float(last["train_loss"]) > float(first["train_loss"]) * 0.9 and float(last["val_loss"]) > float(first["val_loss"]) * 0.9:
        LOG.warning("Possible underfitting: train_loss and val_loss did not improve much.")
    if float(last["val_loss"]) > float(first["val_loss"]) and float(last["train_loss"]) < float(first["train_loss"]):
        LOG.warning("Possible overfitting: val_loss rose while train_loss fell.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data_path", required=True)
    args = parser.parse_args()
    ckpt = train_model(args.station_id, args.target, args.data_path, args.config)
    print(f"saved checkpoint: {ckpt}")


if __name__ == "__main__":
    main()
