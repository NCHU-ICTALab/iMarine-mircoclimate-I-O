from datetime import datetime

from microclimate.models import Observation, UTC
from microclimate.storage import ObservationStore


def test_store_upserts_latest_observation(tmp_path):
    store = ObservationStore(tmp_path / "test.sqlite3")
    obs = Observation("a1", "高雄港", datetime.now(UTC), "A", wind_speed=5)

    assert store.upsert_many([obs]) == 1
    assert store.upsert_many([obs]) == 1

    latest = store.latest_observations()
    assert len(latest) == 1
    assert latest[0].station_name == "高雄港"
