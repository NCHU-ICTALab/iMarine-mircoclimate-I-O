from fastapi.testclient import TestClient

from app.api import app


def test_v35_station_inventory_roles_are_explicit():
    response = TestClient(app).get("/api/v1/dispatch/system-audit?target_area=KHH")
    data = response.json()
    stations = data["dashboard_tables"]["stations"]

    khwd = [row for row in stations if row["station_group"] == "KHWD"]
    nearby = [row for row in stations if row["station_group"] == "nearby_cwa"]
    baseline = [row for row in stations if row["station_id"] == "467441"]

    assert len(khwd) >= 2
    assert len(nearby) >= 1
    assert len(baseline) == 1
    assert all(row["is_port_local_core"] is True for row in khwd)
    assert all(row["is_port_local_core"] is False for row in nearby)
    assert baseline[0]["is_port_local_core"] is False
    assert baseline[0]["is_fallback_baseline"] is True
