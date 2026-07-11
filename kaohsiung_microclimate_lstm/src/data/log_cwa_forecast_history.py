from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_DATA_ID = "F-D0047-091"
DEFAULT_HISTORY_ROOT = Path("data/raw/cwa_forecast_history")
DEFAULT_REPORT_DIR = Path("results/cwa_comparison_v13")


def _cwa_verify_ssl() -> bool:
    """CWA's opendata TLS chain fails strict verification on some OpenSSL builds.

    Mirrors the CWA_VERIFY_SSL toggle already used by fetch_marine_history.py /
    fetch_nearby_cwa_current.py / app/config.py.
    """
    value = os.environ.get("CWA_VERIFY_SSL")
    if value is None:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("CWA_VERIFY_SSL="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return str(value).strip().lower() != "false" if value is not None else True


def write_cwa_forecast_snapshot(
    payload: dict[str, Any],
    data_id: str = DEFAULT_DATA_ID,
    output_root: str | Path = DEFAULT_HISTORY_ROOT,
    fetched_at: datetime | None = None,
) -> Path:
    fetched = fetched_at or datetime.now(TAIPEI)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=TAIPEI)
    out_dir = Path(output_root) / str(data_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{fetched.astimezone(TAIPEI).strftime('%Y%m%d_%H%M')}.json"
    snapshot = {
        "data_id": str(data_id),
        "fetched_at": fetched.astimezone(TAIPEI).isoformat(timespec="seconds"),
        "payload": payload,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def collect_cwa_forecast_history(
    data_id: str = DEFAULT_DATA_ID,
    api_key: str | None = None,
    output_root: str | Path = DEFAULT_HISTORY_ROOT,
    base_url: str = "https://opendata.cwa.gov.tw/api/v1/rest/datastore",
    session: Any | None = None,
    timeout_seconds: int = 20,
    verify_ssl: bool | None = None,
) -> dict[str, Any]:
    import requests

    token = api_key or os.getenv("CWA_API_KEY")
    if not token:
        raise ValueError("CWA API key is required via api_key or CWA_API_KEY.")
    client = session or requests
    verify = verify_ssl if verify_ssl is not None else _cwa_verify_ssl()
    fetched_at = datetime.now(TAIPEI)
    response = client.get(
        f"{base_url.rstrip('/')}/{data_id}",
        params={"Authorization": token, "format": "JSON"},
        timeout=timeout_seconds,
        verify=verify,
    )
    response.raise_for_status()
    payload = response.json()
    path = write_cwa_forecast_snapshot(payload, data_id=data_id, output_root=output_root, fetched_at=fetched_at)
    return {
        "data_id": str(data_id),
        "snapshot_path": str(path),
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
    }


def build_cwa_comparison_readiness_report(
    history_root: str | Path = DEFAULT_HISTORY_ROOT,
    observation_root: str | Path = "data/raw/observed_hourly",
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    data_id: str = DEFAULT_DATA_ID,
    min_days: int = 14,
) -> dict[str, Any]:
    history_dir = Path(history_root) / str(data_id)
    snapshots = sorted(history_dir.glob("*.json")) if history_dir.exists() else []
    snapshot_times = [_snapshot_time(path) for path in snapshots]
    snapshot_times = [time for time in snapshot_times if time is not None]
    forecast_days = _coverage_days(snapshot_times)
    observation_times = _observation_times(Path(observation_root))
    observation_days = _coverage_days(observation_times)
    ready = forecast_days >= int(min_days) and observation_days >= int(min_days)
    blockers = []
    if forecast_days < int(min_days):
        blockers.append(f"forecast history coverage shorter than {min_days} days")
    if observation_days < int(min_days):
        blockers.append(f"matching observation coverage shorter than {min_days} days")
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "data_id": str(data_id),
        "ready": ready,
        "min_required_days": int(min_days),
        "snapshot_count": len(snapshots),
        "forecast_history_coverage_days": forecast_days,
        "observation_coverage_days": observation_days,
        "blockers": blockers,
        "comparison_report_allowed": ready,
    }
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison_readiness_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _snapshot_time(path: Path) -> pd.Timestamp | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = payload.get("fetched_at")
    if value:
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed
    parsed = pd.to_datetime(path.stem, format="%Y%m%d_%H%M", errors="coerce")
    return None if pd.isna(parsed) else parsed.tz_localize(TAIPEI)


def _observation_times(root: Path) -> list[pd.Timestamp]:
    times: list[pd.Timestamp] = []
    if not root.exists():
        return times
    for path in root.glob("*.csv"):
        try:
            frame = pd.read_csv(path, usecols=["obs_time"])
        except Exception:
            continue
        parsed = pd.to_datetime(frame["obs_time"], errors="coerce").dropna()
        times.extend(pd.Timestamp(value) for value in parsed)
    return times


def _coverage_days(times: list[pd.Timestamp]) -> float:
    if len(times) < 2:
        return 0.0
    normalized = [_as_taipei(value) for value in times]
    start = min(normalized)
    end = max(normalized)
    return round(float((end - start).total_seconds() / 86400.0), 3)


def _as_taipei(value: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(TAIPEI)
    return ts.tz_convert(TAIPEI)
