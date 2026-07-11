from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from app.fetch_microclimate import run_microclimate_source_fetch


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_JOBS = {
    "port_local": {"interval_minutes": 10},
    "marine_realtime": {"interval_minutes": 240},
    "nearby_cwa_live": {"interval_minutes": 15},
    "cwa_forecast_history": {"interval_minutes": 180},
}


class MicroclimateFetchScheduler:
    def __init__(self, project_root: str | Path, config_path: str | Path | None = None) -> None:
        self.project_root = Path(project_root)
        self.config_path = Path(config_path) if config_path else self.project_root / "config.yaml"
        self.scheduler: Any | None = None
        self.enabled = False
        self.jobs: dict[str, dict[str, Any]] = {}
        self.last_run: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        config = load_auto_fetch_scheduler_config(self.config_path)
        self.enabled = bool(config.get("enabled", False))
        self.jobs = normalize_scheduler_jobs(config.get("jobs", {}))
        if not self.enabled:
            return self.status()
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except Exception as exc:  # pragma: no cover - depends on optional runtime package
            self.last_run = {"success": False, "error": f"APScheduler unavailable: {exc}"}
            self.enabled = False
            return self.status()
        self.scheduler = BackgroundScheduler(timezone="Asia/Taipei")
        for job_name, job_cfg in self.jobs.items():
            if not bool(job_cfg.get("enabled", True)):
                continue
            self.scheduler.add_job(
                self.run_once,
                "interval",
                minutes=int(job_cfg.get("interval_minutes", 60)),
                id=job_name,
                args=[job_name],
                replace_existing=True,
            )
        self.scheduler.start()
        return self.status()

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None

    def run_once(self, job_name: str = "manual") -> dict[str, Any]:
        result = run_microclimate_source_fetch(self.project_root, self.config_path)
        result["trigger"] = "scheduler"
        result["job_name"] = job_name
        self.last_run = result
        return result

    def status(self) -> dict[str, Any]:
        scheduled_jobs = []
        if not self.jobs:
            config = load_auto_fetch_scheduler_config(self.config_path)
            self.enabled = bool(config.get("enabled", False))
            self.jobs = normalize_scheduler_jobs(config.get("jobs", {}))
        if self.scheduler is not None:
            for job in self.scheduler.get_jobs():
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
                scheduled_jobs.append({"id": job.id, "next_run_time": next_run})
        else:
            now = datetime.now(TAIPEI)
            scheduled_jobs = [
                {
                    "id": name,
                    "next_run_time": None,
                    "interval_minutes": int(cfg.get("interval_minutes", 60)),
                    "enabled": bool(cfg.get("enabled", True)),
                    "preview_next_run_if_enabled": (now + timedelta(minutes=int(cfg.get("interval_minutes", 60)))).isoformat(timespec="seconds"),
                }
                for name, cfg in self.jobs.items()
            ]
        return {
            "enabled": bool(self.enabled and self.scheduler is not None),
            "configured_enabled": bool(self.enabled),
            "config_path": str(self.config_path),
            "jobs": scheduled_jobs,
            "last_run": self.last_run,
        }


def load_auto_fetch_scheduler_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {"enabled": False, "jobs": DEFAULT_JOBS}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    scheduler = data.get("auto_fetch_scheduler", {}) or {}
    return {"enabled": bool(scheduler.get("enabled", False)), "jobs": scheduler.get("jobs", DEFAULT_JOBS)}


def normalize_scheduler_jobs(raw_jobs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for name, defaults in DEFAULT_JOBS.items():
        incoming = raw_jobs.get(name, {}) if isinstance(raw_jobs, dict) else {}
        jobs[name] = {**defaults, **(incoming or {})}
    return jobs
