from __future__ import annotations


LOW_RELIABILITY = {"low", "low_to_medium", "optional", "reference_only", "low_confidence", "unavailable"}

ACTION_LABELS = {
    "normal_dispatch": ("正常派工", "可正常安排作業，持續監測天氣變化。"),
    "observe_only": ("觀察", "風險來源可靠度較低，建議先觀察並加強現場回報。"),
    "monitor": ("監控", "可派工但需提高警戒，持續監控風速、陣風與降雨。"),
    "restrict_sensitive_tasks": ("限制敏感作業", "建議限制吊掛、高處、臨水或其他受天氣影響較大的作業。"),
    "delay_high_risk_tasks": ("延後高風險作業", "不建議安排高風險戶外作業，優先改派低風險工作。"),
    "suspend_exposed_tasks": ("暫停暴露作業", "建議暫停戶外暴露或高風險作業，待風險降低後再復工。"),
}

HIGH_RELIABILITY_ACTION = {
    "normal": "normal_dispatch",
    "watch": "monitor",
    "warning": "restrict_sensitive_tasks",
    "high_risk": "delay_high_risk_tasks",
    "stop": "suspend_exposed_tasks",
}

LOW_RELIABILITY_ACTION = {
    "normal": "normal_dispatch",
    "watch": "observe_only",
    "warning": "monitor",
    "high_risk": "restrict_sensitive_tasks",
    "stop": "delay_high_risk_tasks",
}


def map_dispatch_action_level(dispatch_risk_level: str, primary_trigger_reliability: str) -> dict[str, str]:
    table = LOW_RELIABILITY_ACTION if primary_trigger_reliability in LOW_RELIABILITY else HIGH_RELIABILITY_ACTION
    action = table.get(dispatch_risk_level, "normal_dispatch")
    label, description = ACTION_LABELS[action]
    return {
        "dispatch_action_level": action,
        "action_label": label,
        "action_description": description,
    }
