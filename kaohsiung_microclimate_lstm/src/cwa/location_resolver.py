from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from .pop3h_client import fetch_pop3h
    from .cwa_open_data_client import CwaOpenDataClient, extract_pop_timeseries, infer_source_resolution
except ImportError:  # pragma: no cover
    from pop3h_client import fetch_pop3h
    from cwa_open_data_client import CwaOpenDataClient, extract_pop_timeseries, infer_source_resolution


TZ_TPE = ZoneInfo("Asia/Taipei")


RESOLUTION_SCORE = {"3h": 0, "6h": 1, "12h": 2, "3h_unverified": 3, "6h_unverified": 3, "12h_unverified": 3, "unknown": 4}


def resolve_cwa_location(
    candidates: list[str],
    fallback_location: str,
    api_key: str | None = None,
    project_root: str | Path = "kaohsiung_microclimate_lstm",
) -> dict[str, Any]:
    tested = []
    resolved = None
    for location in candidates:
        result = fetch_pop3h(location, api_key=api_key, cache_minutes=0, project_root=project_root)
        record_count = len(result.get("records", []))
        available = bool(result.get("available", False) or record_count > 0)
        tested.append({"location_name": location, "available": available, "record_count": record_count})
        if available and resolved is None:
            resolved = location
            break
    if resolved is None:
        resolved = fallback_location
    return {
        "resolved_location_name": resolved,
        "tested_locations": tested,
        "resolved_at": datetime.now(tz=TZ_TPE).isoformat(timespec="seconds"),
    }


def load_or_resolve_cwa_location(config: dict[str, Any], project_root: str | Path = "kaohsiung_microclimate_lstm") -> dict[str, Any]:
    project = Path(project_root)
    out = project / "config" / "resolved_cwa_location.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    cwa_cfg = config.get("rain_postprocess", {}).get("cwa_pop3h", {})
    candidates = [str(item) for item in cwa_cfg.get("location_candidates", [])]
    fallback = str(cwa_cfg.get("fallback_location", candidates[0] if candidates else "前鎮區"))
    result = resolve_cwa_location(candidates, fallback, project_root=project)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def resolve_cwa_forecast_source(
    dataset_candidates: list[dict[str, Any]],
    location_candidates: list[str],
    element_name_candidates: dict[str, list[str]],
    api_key: str | None,
    config: dict[str, Any],
    project_root: str | Path = "kaohsiung_microclimate_lstm",
) -> dict[str, Any]:
    cwa_cfg = config.get("cwa_open_data", {})
    cache_cfg = cwa_cfg.get("cache", {})
    retry_cfg = cwa_cfg.get("retry", {})
    client = CwaOpenDataClient(
        api_key=api_key,
        base_url=str(cwa_cfg.get("base_url", "https://opendata.cwa.gov.tw/api/v1/rest/datastore")),
        timeout_seconds=int(cwa_cfg.get("timeout_seconds", 10)),
        cache_minutes=int(cache_cfg.get("cache_minutes", cwa_cfg.get("cache_minutes", 30))),
        cache_dir=Path(project_root) / str(cache_cfg.get("cache_dir", "data/cache/cwa")),
        retry_attempts=int(retry_cfg.get("max_attempts", 3 if retry_cfg.get("enabled", True) else 1)),
        retry_backoff_seconds=float(retry_cfg.get("backoff_seconds", 1)),
    )
    candidates = sorted(dataset_candidates, key=lambda item: int(item.get("priority", 999)))
    pop_elements = element_name_candidates.get("precipitation_probability", [])
    tested: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None

    for dataset in candidates:
        dataset_id = str(dataset.get("dataset_id"))
        for location_idx, location in enumerate(location_candidates):
            for element in pop_elements:
                payload = client.fetch_dataset(dataset_id, location, element)
                timeseries = extract_pop_timeseries(payload.get("json", {}), location, element) if payload.get("available") else []
                resolution = infer_source_resolution(element, timeseries)
                item = {
                    "dataset_id": dataset_id,
                    "location_name": location,
                    "element_name": element,
                    "available": bool(timeseries),
                    "record_count": len(timeseries),
                    "source_resolution": resolution,
                    "dataset_priority": int(dataset.get("priority", 999)),
                    "location_priority": location_idx + 1,
                    **({"reason": payload.get("reason")} if payload.get("reason") else {}),
                }
                tested.append(item)
                if not timeseries:
                    continue
                candidate = {
                    "available": True,
                    "dataset_id": dataset_id,
                    "location_name": location,
                    "element_name": element,
                    "source_resolution": resolution,
                    "valid_times": timeseries,
                    "fetched_at": payload.get("fetched_at"),
                    "score": (RESOLUTION_SCORE.get(resolution, 3), int(dataset.get("priority", 999)), location_idx),
                }
                if best is None or candidate["score"] < best["score"]:
                    best = candidate
                if candidate["score"] == (0, 1, 0):
                    resolved_at = datetime.now(tz=TZ_TPE).isoformat(timespec="seconds")
                    best.pop("score", None)
                    return {**best, "tested": tested, "resolved_at": resolved_at}

    resolved_at = datetime.now(tz=TZ_TPE).isoformat(timespec="seconds")
    if best is None:
        return {
            "available": False,
            "dataset_id": None,
            "location_name": None,
            "element_name": None,
            "source_resolution": "unknown",
            "tested": tested,
            "resolved_at": resolved_at,
        }
    score = best.pop("score")
    return {**best, "tested": tested, "resolved_at": resolved_at}
