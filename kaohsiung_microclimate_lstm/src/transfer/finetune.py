from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

try:
    from ..config import load_config, target_config
    from ..dataset import LSTMDataset, chronological_split
    from ..model import build_model
    from ..preprocess import build_window_bundle, load_observations
    from ..train import compute_loss, move_target, set_seed
except ImportError:  # pragma: no cover
    from config import load_config, target_config
    from dataset import LSTMDataset, chronological_split
    from model import build_model
    from preprocess import build_window_bundle, load_observations
    from train import compute_loss, move_target, set_seed


def align_features_to_source(bundle, source_features: list[str]) -> tuple[np.ndarray, list[str]]:
    """Return X with the same feature order/count used by the source checkpoint."""
    source_features = [str(col) for col in source_features]
    current_index = {col: idx for idx, col in enumerate(bundle.feature_columns)}
    aligned = np.empty((bundle.X.shape[0], bundle.X.shape[1], len(source_features)), dtype=np.float32)
    missing: list[str] = []
    for out_idx, col in enumerate(source_features):
        if col in current_index:
            aligned[:, :, out_idx] = bundle.X[:, :, current_index[col]]
        else:
            missing.append(col)
            aligned[:, :, out_idx] = 0.0 if col == "precipitation_1hr" else 0.5
    return aligned, missing


def finetune_station(
    station_id: str,
    data_path: str | Path,
    config_path: str | Path,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
    source_station: str = "467441",
    target_group: str = "wind_speed_gust",
) -> Path:
    cfg = load_config(config_path)
    set_seed(int(cfg.get("training", {}).get("random_seed", 42)))
    target = target_config(cfg, target_group)
    model_type = target["model_type"]
    if model_type != "multitask_lstm":
        raise ValueError("transfer fine-tune currently supports multitask_lstm only")

    project = Path(project_root)
    source_ckpt_path = project / "models" / "checkpoints" / f"{source_station}_{target_group}_best.pt"
    source_ckpt = torch.load(source_ckpt_path, map_location="cpu")
    df = load_observations(data_path)
    bundle = build_window_bundle(df, cfg, station_id, target_group, project_root)
    if len(bundle.X) < 6:
        return write_zero_shot_marker(project, station_id, source_ckpt_path, reason=f"valid_windows={len(bundle.X)}")

    source_features = [str(col) for col in source_ckpt.get("feature_columns", [])]
    if not source_features:
        raise ValueError(f"Source checkpoint has no feature_columns: {source_ckpt_path}")
    aligned_X, filled_features = align_features_to_source(bundle, source_features)

    model = build_model(model_type, int(source_ckpt["n_features"]), source_ckpt["config"].get("model", {}))
    model.load_state_dict(source_ckpt["model_state"])
    for name, param in model.named_parameters():
        if name.startswith("encoder."):
            param.requires_grad = False

    trainable = [p for p in model.parameters() if p.requires_grad]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    train_sl, val_sl, _ = chronological_split(len(aligned_X), float(cfg["data"]["train_ratio"]), float(cfg["data"]["val_ratio"]))
    train_ds = LSTMDataset(aligned_X[train_sl], bundle.y_anchors[train_sl], model_type)
    val_ds = LSTMDataset(aligned_X[val_sl], bundle.y_anchors[val_sl], model_type)
    train_loader = DataLoader(train_ds, batch_size=int(cfg["training"].get("batch_size", 8)), shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=int(cfg["training"].get("batch_size", 8)), shuffle=False)
    optimizer = torch.optim.Adam(trainable, lr=float(cfg["training"].get("finetune_lr", 5e-5)))
    best_val = float("inf")
    ckpt_path = project / "models" / "checkpoints" / f"{station_id}_{target_group}_finetuned.pt"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    logs: list[dict[str, Any]] = []
    for epoch in range(1, int(cfg["training"].get("finetune_epochs", 30)) + 1):
        model.train()
        train_losses = []
        for X, y in train_loader:
            X = X.to(device)
            y = move_target(y, device)
            optimizer.zero_grad(set_to_none=True)
            loss = compute_loss(model_type, model(X), y)
            loss.backward()
            nn.utils.clip_grad_norm_(trainable, float(cfg["training"].get("gradient_clip", 1.0)))
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        model.eval()
        val_losses = []
        with torch.no_grad():
            for X, y in val_loader:
                X = X.to(device)
                y = move_target(y, device)
                val_losses.append(float(compute_loss(model_type, model(X), y).detach().cpu()))
        val_loss = float(np.mean(val_losses))
        logs.append({"epoch": epoch, "train_loss": float(np.mean(train_losses)), "val_loss": val_loss})
        if val_loss < best_val:
            best_val = val_loss
            torch.save(
                {
                    **source_ckpt,
                    "model_state": model.state_dict(),
                    "station_id": station_id,
                    "transfer_source": source_station,
                    "target_group": target_group,
                    "feature_columns": source_features,
                    "target_station_native_feature_columns": bundle.feature_columns,
                    "filled_source_features": filled_features,
                    "target_columns": bundle.target_columns,
                    "n_features": int(aligned_X.shape[-1]),
                    "model_version": "baseline_lstm_v2_finetuned",
                    "best_val_loss": best_val,
                },
                ckpt_path,
            )
    log_path = project / "logs" / "training" / f"{station_id}_{target_group}_finetune.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
    return ckpt_path


def write_zero_shot_marker(project: Path, station_id: str, source_ckpt_path: Path, reason: str) -> Path:
    out = project / "models" / "checkpoints" / f"{station_id}_wind_speed_gust_pretrain_only.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "station_id": station_id,
                "target_group": "wind_speed_gust",
                "mode": "zero_shot_transfer",
                "source_checkpoint": str(source_ckpt_path),
                "accuracy_grade": "low_confidence",
                "reason": reason,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station_id", required=True)
    parser.add_argument("--data_path", required=True)
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config_hourly_observed.yaml")
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    parser.add_argument("--source_station", default="467441")
    args = parser.parse_args()
    print(finetune_station(args.station_id, args.data_path, args.config, args.project_root, args.source_station))


if __name__ == "__main__":
    main()
