from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import numpy as np


class TimeSeriesValidator:
    """Expanding-window time-series validation with an optional gap."""

    def __init__(self, n_splits: int = 5, test_size: int | float | None = None, gap: int = 0) -> None:
        if n_splits < 1:
            raise ValueError("n_splits must be >= 1")
        if test_size is not None and test_size <= 0:
            raise ValueError("test_size must be positive")
        if gap < 0:
            raise ValueError("gap must be >= 0")
        self.n_splits = int(n_splits)
        self.test_size = test_size
        self.gap = int(gap)

    def split(self, X: Any, y: Any | None = None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        if self.test_size is None:
            test_size = max(1, n // (self.n_splits + 1))
        elif self.test_size < 1:
            test_size = max(1, int(n * float(self.test_size)))
        else:
            test_size = int(self.test_size)
        min_required = self.n_splits * test_size + self.gap + 1
        if n < min_required:
            raise ValueError(f"Need at least {min_required} samples, got {n}")
        indices = np.arange(n)
        first_test_start = n - self.n_splits * test_size
        for split_idx in range(self.n_splits):
            test_start = first_test_start + split_idx * test_size
            train_end = test_start - self.gap
            test_end = test_start + test_size
            yield indices[:train_end], indices[test_start:test_end]

    def validate(self, model: Any, X: Any, y: Any, metric_func: Callable[[Any, Any], float]) -> dict[str, Any]:
        scores: list[float] = []
        folds: list[dict[str, Any]] = []
        x_arr = np.asarray(X)
        y_arr = np.asarray(y)
        for fold, (train_idx, test_idx) in enumerate(self.split(x_arr, y_arr), start=1):
            estimator = _fresh_estimator(model)
            estimator.fit(x_arr[train_idx], y_arr[train_idx])
            pred = estimator.predict(x_arr[test_idx])
            score = float(metric_func(y_arr[test_idx], pred))
            scores.append(score)
            folds.append({"fold": fold, "train_size": int(len(train_idx)), "test_size": int(len(test_idx)), "score": score})
        return {"scores": scores, "mean_score": float(np.mean(scores)), "std_score": float(np.std(scores)), "folds": folds}


class RollingWindowValidator:
    """Fixed-size rolling-window validation for operational backtests."""

    def __init__(self, train_size: int, test_size: int, step_size: int | None = None) -> None:
        if train_size < 1 or test_size < 1:
            raise ValueError("train_size and test_size must be >= 1")
        self.train_size = int(train_size)
        self.test_size = int(test_size)
        self.step_size = int(step_size or test_size)
        if self.step_size < 1:
            raise ValueError("step_size must be >= 1")

    def split(self, X: Any, y: Any | None = None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        indices = np.arange(n)
        start = 0
        while start + self.train_size + self.test_size <= n:
            train_idx = indices[start : start + self.train_size]
            test_idx = indices[start + self.train_size : start + self.train_size + self.test_size]
            yield train_idx, test_idx
            start += self.step_size


def _fresh_estimator(model: Any) -> Any:
    try:
        from sklearn.base import clone

        return clone(model)
    except Exception:
        return model
