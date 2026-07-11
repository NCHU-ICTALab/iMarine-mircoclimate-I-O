from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


TAIPEI = timezone(timedelta(hours=8))


def run_microclimate_source_fetch(project_root: str | Path, config_path: str | Path | None = None) -> dict[str, Any]:
    project = Path(project_root)
    cfg = Path(config_path) if config_path else project / "config.yaml"
    observed_dir = project / "data" / "raw" / "observed_hourly"
    started_at = datetime.now(TAIPEI)
    tasks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("port_local", lambda: _fetch_port_local(project, cfg)),
        ("marine_realtime", lambda: _fetch_marine_realtime(observed_dir)),
        ("nearby_cwa_live", lambda: _fetch_nearby_cwa_live(observed_dir)),
        ("cwa_forecast_history", lambda: _fetch_cwa_forecast_history(project)),
    ]
    results: dict[str, Any] = {}
    success_count = 0
    for name, task in tasks:
        try:
            payload = task()
            results[name] = {"success": True, "result": payload}
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            results[name] = {"success": False, "error": str(exc)}
    return {
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "success": success_count == len(tasks),
        "success_count": success_count,
        "task_count": len(tasks),
        "tasks": results,
        "notes": {
            "marine_realtime": "Uses O-B0075-001 rolling realtime observations. O-B0075-002 30-day history is intentionally not fetched on every manual refresh.",
            "cwa_forecast_history": "Records current forecast release snapshots for later no-leakage CWA comparison readiness.",
        },
    }


def _fetch_port_local(project: Path, config_path: Path) -> dict[str, Any]:
    from kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations import run_fetch_port_local_stations

    return run_fetch_port_local_stations(config_path=config_path, project_root=project)


def _fetch_marine_realtime(observed_dir: Path) -> dict[str, Any]:
    from kaohsiung_microclimate_lstm.src.data.fetch_marine_history import fetch_marine_history

    return fetch_marine_history(dataid="O-B0075-001", output_dir=observed_dir, append=True)


def _fetch_nearby_cwa_live(observed_dir: Path) -> dict[str, Any]:
    from kaohsiung_microclimate_lstm.src.data.fetch_nearby_cwa_current import fetch_nearby_cwa_current

    return fetch_nearby_cwa_current(output_dir=observed_dir, append=True)


def _fetch_cwa_forecast_history(project: Path) -> dict[str, Any]:
    from kaohsiung_microclimate_lstm.src.data.log_cwa_forecast_history import collect_cwa_forecast_history

    return collect_cwa_forecast_history(
        data_id="F-D0047-091",
        output_root=project / "data" / "raw" / "cwa_forecast_history",
    )
