from __future__ import annotations

from typing import Any

import pandas as pd


def check_port_local_dataset_readiness(dataset: pd.DataFrame, config: dict) -> dict[str, Any]:
    training_cfg = config.get("port_local_training", {})
    min_total = int(training_cfg.get("min_total_samples", 500))
    min_labels = int(training_cfg.get("min_valid_label_samples_per_horizon", 100))
    min_days = float(training_cfg.get("min_training_days", 14))
    max_feature_missing = float(training_cfg.get("max_feature_missing_ratio", 0.30))
    max_label_missing = float(training_cfg.get("max_label_missing_ratio", 0.30))

    sample_count = int(len(dataset)) if dataset is not None else 0
    failed: list[str] = []
    warnings: list[str] = []
    time_start = None
    time_end = None
    training_days = 0.0
    if dataset is not None and not dataset.empty and "obs_time" in dataset.columns:
        times = pd.to_datetime(dataset["obs_time"], errors="coerce")
        if not times.isna().all():
            start = times.min()
            end = times.max()
            time_start = start.isoformat()
            time_end = end.isoformat()
            training_days = max(0.0, (end - start).total_seconds() / 86400.0)

    if sample_count < min_total:
        failed.append("sample_count below min_total_samples")
    if training_days < min_days:
        failed.append("training_days below min_training_days")

    if dataset is None or dataset.empty:
        return {
            "ready": False,
            "sample_count": sample_count,
            "min_total_samples": min_total,
            "time_start": time_start,
            "time_end": time_end,
            "training_days": training_days,
            "min_training_days": min_days,
            "missing_ratio": {"features": 1.0, "labels": 1.0},
            "label_valid_count": {},
            "failed_reasons": failed or ["dataset is empty"],
            "warnings": warnings,
        }

    label_columns = [col for col in dataset.columns if col.startswith("target_")]
    feature_columns = [col for col in dataset.columns if col not in {"obs_time", *label_columns}]
    feature_missing_by_column = dataset[feature_columns].isna().mean().to_dict() if feature_columns else {}
    label_missing_by_column = dataset[label_columns].isna().mean().to_dict() if label_columns else {}
    max_feature_ratio = max(feature_missing_by_column.values(), default=1.0)
    max_label_ratio = max(label_missing_by_column.values(), default=1.0)
    if max_feature_ratio > max_feature_missing:
        failed.append("feature missing ratio above threshold")
    if max_label_ratio > max_label_missing:
        failed.append("label missing ratio above threshold")
    if not label_columns:
        failed.append("no target label columns available")

    label_valid_count: dict[str, int] = {}
    for horizon in ["H1", "H2", "H3", "H4"]:
        horizon_cols = [col for col in label_columns if col.endswith(f"_{horizon}")]
        if not horizon_cols:
            label_valid_count[horizon] = 0
            failed.append(f"{horizon} valid labels below threshold")
            continue
        valid_count = int(dataset[horizon_cols].notna().all(axis=1).sum())
        label_valid_count[horizon] = valid_count
        if valid_count < min_labels:
            failed.append(f"{horizon} valid labels below threshold")

    return {
        "ready": not failed,
        "sample_count": sample_count,
        "min_total_samples": min_total,
        "time_start": time_start,
        "time_end": time_end,
        "training_days": round(training_days, 3),
        "min_training_days": min_days,
        "missing_ratio": {
            "features": round(float(max_feature_ratio), 4),
            "labels": round(float(max_label_ratio), 4),
            "feature_by_column": {key: round(float(value), 4) for key, value in feature_missing_by_column.items()},
            "label_by_column": {key: round(float(value), 4) for key, value in label_missing_by_column.items()},
        },
        "label_valid_count": label_valid_count,
        "failed_reasons": failed,
        "warnings": warnings,
    }
