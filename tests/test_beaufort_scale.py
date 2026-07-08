from kaohsiung_microclimate_lstm.src.risk.beaufort_scale import map_mps_to_beaufort


def test_beaufort_boundaries():
    assert map_mps_to_beaufort(0.0)["scale"] == 0
    assert map_mps_to_beaufort(1.0)["scale"] == 1
    assert map_mps_to_beaufort(4.0)["scale"] == 3
    assert map_mps_to_beaufort(8.5)["scale"] == 5
    assert map_mps_to_beaufort(12.0)["scale"] == 6
    assert map_mps_to_beaufort(15.0)["scale"] == 7
    assert map_mps_to_beaufort(18.0)["scale"] == 8
    assert map_mps_to_beaufort(21.0)["scale"] == 9
    assert map_mps_to_beaufort(33.0)["scale"] == 12
