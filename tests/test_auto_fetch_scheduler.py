import sys
import types

from app.scheduler import MicroclimateFetchScheduler, load_auto_fetch_scheduler_config, normalize_scheduler_jobs


def test_load_auto_fetch_scheduler_config_defaults_to_disabled(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("project: {model_version: test}\n", encoding="utf-8")

    loaded = load_auto_fetch_scheduler_config(config)

    assert loaded["enabled"] is False
    assert "port_local" in loaded["jobs"]


def test_normalize_scheduler_jobs_keeps_required_four_jobs():
    jobs = normalize_scheduler_jobs({"nearby_cwa_live": {"interval_minutes": 5}})

    assert jobs["port_local"]["interval_minutes"] == 10
    assert jobs["marine_realtime"]["interval_minutes"] == 240
    assert jobs["nearby_cwa_live"]["interval_minutes"] == 5
    assert jobs["cwa_forecast_history"]["interval_minutes"] == 180


def test_enabled_scheduler_registers_four_interval_jobs_without_real_background_thread(tmp_path, monkeypatch):
    class FakeBackgroundScheduler:
        instances = []

        def __init__(self, timezone):
            self.timezone = timezone
            self.added_jobs = []
            self.started = False
            FakeBackgroundScheduler.instances.append(self)

        def add_job(self, func, trigger, minutes, id, args, replace_existing):
            self.added_jobs.append(
                {
                    "func": func,
                    "trigger": trigger,
                    "minutes": minutes,
                    "id": id,
                    "args": args,
                    "replace_existing": replace_existing,
                }
            )

        def start(self):
            self.started = True

        def get_jobs(self):
            return []

    scheduler_module = types.ModuleType("apscheduler.schedulers.background")
    scheduler_module.BackgroundScheduler = FakeBackgroundScheduler
    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", scheduler_module)

    config = tmp_path / "config.yaml"
    config.write_text(
        """
auto_fetch_scheduler:
  enabled: true
  jobs:
    port_local:
      interval_minutes: 10
    marine_realtime:
      interval_minutes: 240
    nearby_cwa_live:
      interval_minutes: 15
    cwa_forecast_history:
      interval_minutes: 180
""".lstrip(),
        encoding="utf-8",
    )

    scheduler = MicroclimateFetchScheduler(tmp_path, config)
    status = scheduler.start()

    fake_scheduler = FakeBackgroundScheduler.instances[0]
    assert status["configured_enabled"] is True
    assert status["enabled"] is True
    assert fake_scheduler.started is True
    assert {job["id"] for job in fake_scheduler.added_jobs} == {
        "port_local",
        "marine_realtime",
        "nearby_cwa_live",
        "cwa_forecast_history",
    }
    assert {job["id"]: job["minutes"] for job in fake_scheduler.added_jobs} == {
        "port_local": 10,
        "marine_realtime": 240,
        "nearby_cwa_live": 15,
        "cwa_forecast_history": 180,
    }
