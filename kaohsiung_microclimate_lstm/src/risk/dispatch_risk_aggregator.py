from __future__ import annotations

from typing import Any

from .level_mapping import LEVEL_ORDER


SUGGESTIONS = {
    "normal": "可正常派工，持續監測天氣變化。",
    "watch": "可派工但需提高警戒，留意降雨、風速與陣風變化。",
    "warning": "建議限制高風險作業，必要作業需加強現場管制。",
    "high_risk": "不建議安排高風險戶外作業，應啟動替代排程。",
    "stop": "建議停止戶外暴露或高風險作業，待風險降低後再復工。",
}


def max_level(levels: list[str | None]) -> str:
    valid = [level for level in levels if level in LEVEL_ORDER]
    if not valid:
        return "normal"
    return max(valid, key=lambda level: LEVEL_ORDER[level])


def dispatch_suggestion(level: str) -> str:
    return SUGGESTIONS.get(level, SUGGESTIONS["normal"])


def aggregate_dispatch_risk(
    rain_levels: dict[str, str],
    wind_levels: dict[str, str],
    gust_levels: dict[str, str],
    visibility_levels: dict[str, str] | None = None,
    tide_levels: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    anchors = sorted(set(rain_levels) | set(wind_levels) | set(gust_levels))
    visibility_levels = visibility_levels or {}
    tide_levels = tide_levels or {}
    return {
        anchor: max_level(
            [
                rain_levels.get(anchor),
                wind_levels.get(anchor),
                gust_levels.get(anchor),
                visibility_levels.get(anchor),
                tide_levels.get(anchor),
            ]
        )
        for anchor in anchors
    }
