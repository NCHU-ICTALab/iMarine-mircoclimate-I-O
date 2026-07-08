from __future__ import annotations


BEAUFORT_SCALE = [
    (0, 0.0, 0.3, "無風", "<0.3"),
    (1, 0.3, 1.6, "軟風", "0.3-1.5"),
    (2, 1.6, 3.4, "輕風", "1.6-3.3"),
    (3, 3.4, 5.5, "微風", "3.4-5.4"),
    (4, 5.5, 8.0, "和風", "5.5-7.9"),
    (5, 8.0, 10.8, "清風", "8.0-10.7"),
    (6, 10.8, 13.9, "強風", "10.8-13.8"),
    (7, 13.9, 17.2, "疾風", "13.9-17.1"),
    (8, 17.2, 20.8, "大風", "17.2-20.7"),
    (9, 20.8, 24.5, "烈風", "20.8-24.4"),
    (10, 24.5, 28.5, "狂風", "24.5-28.4"),
    (11, 28.5, 32.7, "暴風", "28.5-32.6"),
    (12, 32.7, float("inf"), "颶風", ">=32.7"),
]


def map_mps_to_beaufort(wind_mps: float) -> dict[str, object]:
    value = max(0.0, float(wind_mps))
    for scale, lower, upper, label, range_mps in BEAUFORT_SCALE:
        if lower <= value < upper:
            return {"scale": scale, "label_zh": label, "range_mps": range_mps}
    scale, _, _, label, range_mps = BEAUFORT_SCALE[-1]
    return {"scale": scale, "label_zh": label, "range_mps": range_mps}
