from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import torch
    from torch.utils.data import Dataset, WeightedRandomSampler
except ImportError:  # pragma: no cover - train/evaluate require torch
    torch = None
    Dataset = object  # type: ignore[assignment,misc]
    WeightedRandomSampler = object  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class WindowBundle:
    X: np.ndarray
    y_full: np.ndarray
    y_anchors: np.ndarray
    target_columns: list[str]
    feature_columns: list[str]
    anchor_offsets_minutes: list[int]
    timestamps: np.ndarray
    persistence: np.ndarray


def create_windows(
    data: np.ndarray,
    lookback: int,
    full_steps: int,
    target_col_indices: list[int],
    anchor_idx: list[int],
    invalid_mask: np.ndarray,
    timestamps: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X: list[np.ndarray] = []
    y_full: list[np.ndarray] = []
    y_anchors: list[np.ndarray] = []
    ts: list[object] = []
    persistence: list[np.ndarray] = []
    target_idx = np.asarray(target_col_indices, dtype=int)
    for i in range(lookback, len(data) - full_steps + 1):
        if invalid_mask[i - lookback : i + full_steps].any():
            continue
        history = data[i - lookback : i]
        future = data[i : i + full_steps][:, target_idx]
        X.append(history)
        y_full.append(future)
        y_anchors.append(future[anchor_idx])
        persistence.append(np.repeat(history[-1, target_idx][None, :], len(anchor_idx), axis=0))
        if timestamps is not None:
            ts.append(timestamps[i])
    return (
        np.asarray(X, dtype=np.float32),
        np.asarray(y_full, dtype=np.float32),
        np.asarray(y_anchors, dtype=np.float32),
        np.asarray(ts, dtype=object),
        np.asarray(persistence, dtype=np.float32),
    )


class LSTMDataset(Dataset):  # type: ignore[misc]
    def __init__(self, X: np.ndarray, y: np.ndarray, model_type: str, rain_threshold: float = 0.1) -> None:
        if torch is None:
            raise RuntimeError("torch is required to use LSTMDataset")
        self.X = torch.as_tensor(X, dtype=torch.float32)
        self.y = torch.as_tensor(y, dtype=torch.float32)
        self.model_type = model_type
        self.rain_threshold = float(rain_threshold)

    def __len__(self) -> int:
        return int(self.X.shape[0])

    def __getitem__(self, idx: int):
        y = self.y[idx]
        if self.model_type == "twostage_lstm":
            amount = y.squeeze(-1) if y.ndim == 2 else y
            binary = (amount > self.rain_threshold).float()
            return self.X[idx], {"amount": amount, "binary": binary}
        if self.model_type == "lstm":
            return self.X[idx], y.squeeze(-1)
        return self.X[idx], y


def chronological_split(n: int, train_ratio: float, val_ratio: float) -> tuple[slice, slice, slice]:
    if n < 3:
        raise ValueError("Need at least 3 windows for train/val/test split")
    train_end = max(1, int(n * train_ratio))
    val_end = max(train_end + 1, int(n * (train_ratio + val_ratio)))
    val_end = min(val_end, n - 1)
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)


def build_precipitation_sampler(dataset: LSTMDataset) -> WeightedRandomSampler:
    if torch is None:
        raise RuntimeError("torch is required to build a precipitation sampler")
    labels = torch.stack([dataset[i][1]["binary"][0] for i in range(len(dataset))])
    n_no_rain = int((labels == 0).sum().item())
    n_rain = int((labels == 1).sum().item())
    weight_no_rain = 1.0
    weight_rain = n_no_rain / max(n_rain, 1)
    sample_weights = torch.where(
        labels == 1,
        torch.full_like(labels, weight_rain, dtype=torch.float),
        torch.full_like(labels, weight_no_rain, dtype=torch.float),
    )
    return WeightedRandomSampler(weights=sample_weights, num_samples=len(sample_weights), replacement=True)
