from fastapi.testclient import TestClient

from app.api import app


def test_v35_dataset_duration_allows_unknown_but_not_fake_zero():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    data = response.json()

    for dataset in data["dataset_duration_summary"].values():
        if dataset.get("status") == "not_available":
            assert dataset.get("duration_days") is None
            assert dataset.get("total_rows") is None
        else:
            assert dataset.get("duration_days") is None or dataset.get("duration_days") >= 0
            assert dataset.get("total_rows") is None or dataset.get("total_rows") > 0
