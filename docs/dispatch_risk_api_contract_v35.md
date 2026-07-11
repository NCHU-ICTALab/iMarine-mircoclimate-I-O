# Dispatch Risk API Contract v3.5

模型版本：`kaohsiung_port_dispatch_risk_v3.5`

## 版本定位

v3.5 是系統盤點與派工風險輸出對齊版。此版本不重訓 `port_local_model`，不改 model selection engine，不改 KHWD parser，也不改 nearby CWA training pipeline；主要補齊系統盤點、資料來源盤點、測站盤點、資料期間、模型誤差指標、前端 dashboard payload，以及 CWA 官方 +3h/+6h 延伸預報視窗。

## Endpoints

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&no_realtime_khwd_mode=true
GET /api/v1/dispatch/model-status?target_area=KHH
GET /api/v1/dispatch/station-usage?target_area=KHH
GET /api/v1/dispatch/system-audit?target_area=KHH
```

## Required Invariants

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

## Dispatch Risk Response

`GET /api/v1/dispatch/risk?target_area=KHH` 必須保留：

```text
model_version
generated_at
target_area
prediction_mode
forecast_anchors
extended_forecast_windows
cwa
data_availability
reliability
station_priority_summary
model_selection_summary
current_station_usage
station_display_rows
trace
```

### H1-H4 Nowcast

`forecast_anchors` 維持 H1~H4（30/60/90/120 分鐘）短期派工視窗，來源可為 `port_local_postprocess`、`nearby_cwa_historical_model` 或最後備援，不得混入 +3h/+6h 官方預報。

### CWA +3h/+6h Official Windows

`extended_forecast_windows` 是獨立欄位，不屬於 H1~H4 模型外插。資料來源為 CWA `F-D0047-065`，降雨機率使用 `3小時降雨機率`，風速以官方蒲福風級區間呈現，不提供精確 m/s。

```json
{
  "available": true,
  "source": "cwa_official_forecast",
  "data_id": "F-D0047-065",
  "location_name": "前鎮區",
  "windows": [
    {
      "window": "+3h",
      "offset_minutes": 180,
      "source": "cwa_official_forecast",
      "wind_speed": {
        "available": true,
        "value_mps": null,
        "beaufort_scale_min": 6,
        "beaufort_scale_text": ">= 6",
        "wind_speed_text": ">= 11",
        "operation_level": null,
        "basis": "cwa_beaufort_scale_range_not_precise_value"
      },
      "rain_probability": {"available": true, "value": 0.1, "level": "normal"},
      "wind_gust": {"available": false, "reason": "no_official_cwa_gust_product"},
      "visibility": {"available": false, "reason": "no_official_cwa_visibility_product"}
    }
  ]
}
```

Frontend 相容簡化欄位 `cwa` 對齊 iMarine-FrontEnd `CwaWindow`：

```json
[
  {"window": "+3h", "rainLevel": "無", "beaufort": 6},
  {"window": "+6h", "rainLevel": "無", "beaufort": 6}
]
```

CWA API 失敗時，`extended_forecast_windows.available` 必須為 `false`，`cwa` 必須為空陣列，且不得影響 `forecast_anchors`。

## Live Verification

已用 `scripts/verify_cwa_extended_forecast_live.py` 實際呼叫 CWA API 驗證：

```text
data_id: F-D0047-065
location_name: 前鎮區
current_rain_probability: 0.1
next_rain_probability: 0.1
current_wind: wind_speed_text >= 11, beaufort_scale_min 6
next_wind: wind_speed_text >= 11, beaufort_scale_min 6
passed: true
```

報告：`kaohsiung_microclimate_lstm/results/dispatch_risk_v35/cwa_extended_forecast_live_verification.json`

## system-audit Response

`GET /api/v1/dispatch/system-audit?target_area=KHH` 必須保留：

```text
model_version
target_area
generated_at
system_status_summary
data_source_summary
station_summary
dataset_duration_summary
model_accuracy_summary
model_selection_summary
current_station_usage
dashboard_cards
dashboard_tables
trace
```

## Reports

```text
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/system_audit_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/data_source_inventory_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/station_inventory_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/dataset_duration_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_accuracy_summary_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_selection_summary_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/ui_dashboard_payload_v35.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/api_contract_snapshot_v35.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/prediction_samples_v35.json
```

## Data Source Roles

```text
KHWD = port-local realtime wind/gust source
nearby CWA historical = fallback historical model training reference
467441 = fallback baseline only
CWA PoP = rain prior only
CWA +3h/+6h = official forecast display only
```

## Current Validated State

```text
normal_prediction_mode: port_local_postprocess
no_realtime_khwd_mode_selected: nearby_cwa_historical_model
nearby_cwa_historical_model: trained / available / accepted
port_local_model: disabled / not trained
fallback_baseline: available_last_resort_only
```
