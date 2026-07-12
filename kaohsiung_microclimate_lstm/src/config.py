from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from math import ceil
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
_CONFIG_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_absolute() and not config_path.exists():
        config_path = ROOT / config_path
    config_path = config_path.resolve()
    stat = config_path.stat()
    cache_key = (str(config_path), int(stat.st_mtime_ns), int(stat.st_size))
    if cache_key in _CONFIG_CACHE:
        return deepcopy(_CONFIG_CACHE[cache_key])
    with config_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    validate_config(cfg)
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE[cache_key] = cfg
    return deepcopy(cfg)


def validate_config(cfg: dict[str, Any]) -> None:
    required = ["time_step_minutes", "lookback_hours", "horizon_minutes", "anchor_offsets_minutes", "targets"]
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(missing)}")
    step = int(cfg["time_step_minutes"])
    horizon = int(cfg["horizon_minutes"])
    if horizon % step != 0:
        raise ValueError("horizon_minutes must be divisible by time_step_minutes")
    full_steps = horizon // step
    anchor_idx = anchor_indices(cfg)
    if any(idx < 0 or idx >= full_steps for idx in anchor_idx):
        raise ValueError("anchor_offsets_minutes must fall within horizon_minutes")


def lookback_steps(cfg: dict[str, Any], target_group: str | None = None) -> int:
    lookback_hours = cfg["lookback_hours"]
    if target_group:
        target = cfg.get("targets", {}).get(target_group, {})
        lookback_hours = target.get("lookback_hours", lookback_hours)
    return int(float(lookback_hours) * 60 / int(cfg["time_step_minutes"]))


def full_steps(cfg: dict[str, Any]) -> int:
    return int(int(cfg["horizon_minutes"]) / int(cfg["time_step_minutes"]))


def anchor_indices(cfg: dict[str, Any]) -> list[int]:
    step = int(cfg["time_step_minutes"])
    return [max(0, int(ceil(offset / step)) - 1) for offset in cfg["anchor_offsets_minutes"]]


def target_config(cfg: dict[str, Any], target_group: str) -> dict[str, Any]:
    try:
        return cfg["targets"][target_group]
    except KeyError as exc:
        choices = ", ".join(sorted(cfg.get("targets", {})))
        raise ValueError(f"Unknown target_group {target_group!r}. Available: {choices}") from exc
