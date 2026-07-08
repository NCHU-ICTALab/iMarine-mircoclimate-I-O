from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Any


def get_cached(cache_path: str | Path, ttl_seconds: int, fetch_fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(cached.get("_cached_at", 0)) < ttl_seconds:
            return cached
    data = fetch_fn()
    data["_cached_at"] = time.time()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
