import json
from concurrent.futures import ThreadPoolExecutor

from kaohsiung_microclimate_lstm.src import io_utils
from kaohsiung_microclimate_lstm.src.io_utils import atomic_write_json


def test_atomic_write_json_handles_concurrent_writes_to_same_path(tmp_path):
    target = tmp_path / "dataset_readiness_report.json"

    def write_report(index: int) -> None:
        atomic_write_json(target, {"writer": index, "status": "ok"})

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(write_report, range(36)))

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["writer"] in range(36)
    assert list(tmp_path.glob(".dataset_readiness_report.json.*.tmp")) == []


def test_atomic_write_json_retries_transient_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "system_audit_report.json"
    real_replace = io_utils.os.replace
    calls = {"count": 0}

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("simulated Windows file lock")
        return real_replace(src, dst)

    monkeypatch.setattr(io_utils.os, "replace", flaky_replace)

    atomic_write_json(target, {"ready": True}, retry_delay_seconds=0)

    assert calls["count"] == 2
    assert json.loads(target.read_text(encoding="utf-8")) == {"ready": True}
