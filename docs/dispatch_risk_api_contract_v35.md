# Dispatch Risk API Contract v3.5

版本：`kaohsiung_port_dispatch_risk_v3.5`

## 目的

v3.5 是 System Audit + Data/Station/Model Summary Dashboard patch。此版本不重訓 `port_local_model`，不改 model selection engine，不改 KHWD parser，也不改 nearby CWA training pipeline；主要補齊系統盤點、資料來源盤點、測站盤點、資料期間、模型誤差指標與前端 dashboard payload。

## Endpoint

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

## system-audit Response

`GET /api/v1/dispatch/system-audit?target_area=KHH` 必須回傳：

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

v3.5 產出：

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
```

## Dataset Duration Rules

- 可讀到 timestamp / obs_time 時才計算 `time_start`、`time_end`、`duration_days`、`total_rows`。
- 讀不到資料時使用 `status: not_available` 與 `reason`。
- 不得把未知資料期間偽造成 `0 days`。
- 不得把未知 row count 偽造成 `0`。

## Model Accuracy Rules

- wind_speed / wind_gust 是 regression，顯示 MAE、RMSE、R2，不稱為 accuracy。
- rain_probability 顯示 Brier Score、POD、FAR、AUC。
- 缺 metrics 時使用 `metrics_available: false` 與 `metrics_status: not_available`，不得偽造 metrics。

## Current Validated State

```text
normal_prediction_mode: port_local_postprocess
no_realtime_khwd_mode_selected: nearby_cwa_historical_model
nearby_cwa_historical_model: trained / available / accepted
port_local_model: disabled / not trained
fallback_baseline: available_last_resort_only
```

目前主要指標：

```text
wind_speed H1 MAE: 0.5919 m/s
wind_gust H1 MAE: 0.6835 m/s
rain_probability H1 Brier Score: 0.0183
```
