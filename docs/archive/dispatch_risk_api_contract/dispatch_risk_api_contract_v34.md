# Dispatch Risk API Contract v3.4

版本：`kaohsiung_port_dispatch_risk_v3.4`

## 目的

v3.4 在 v3.3 deterministic model selection 基礎上，加入 training orchestration、model registry、model manifest validation，以及前端可直接使用的 station usage payload。

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
GET /api/v1/dispatch/risk?target_area=KHH&no_realtime_khwd_mode=true
GET /api/v1/dispatch/model-status?target_area=KHH
GET /api/v1/dispatch/station-usage?target_area=KHH
```

`no_realtime_khwd_mode=true` 只影響當次 request 的 model selection，不會刪除或修改 KHWD CSV。

## Prediction Chain

```text
port_local_model
port_local_postprocess
nearby_cwa_historical_model
fallback_baseline
```

正常 KHWD 可用時，選擇 `port_local_postprocess`。若 KHWD 在當次 request 被停用或不可用，且 nearby CWA historical model 已訓練並驗收通過，選擇 `nearby_cwa_historical_model`。

## Required Invariants

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

角色定義：

```text
KHWD = port-local realtime / port-local core station
nearby CWA stations = historical fallback training reference
467441 = fallback baseline only
CWA PoP = rain prior only
```

## Required Top-level Fields

```text
model_version
prediction_mode
model_selection_summary
model_training_status
model_registry_summary
station_priority_summary
current_station_usage
station_display_rows
nearby_cwa_historical_summary
forecast_anchors
data_availability
trace
```

## model_training_status

目前已驗證的正常狀態：

```json
{
  "training_checked": true,
  "training_required": false,
  "training_skipped": true,
  "skip_reason": "Existing accepted nearby CWA historical model found.",
  "available_models": {
    "port_local_model": {
      "trained": false,
      "available": false,
      "accepted": false
    },
    "nearby_cwa_historical_model": {
      "trained": true,
      "available": true,
      "accepted": true,
      "artifact_version": "nearby_cwa_v34",
      "selected_station_ids": ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"]
    }
  }
}
```

## current_station_usage

KHWD 正常可用：

```json
{
  "selected_prediction_mode": "port_local_postprocess",
  "active_wind_source": "KHWD",
  "active_gust_source": "KHWD",
  "active_rain_source": "nearby_cwa_historical_rain_model_plus_cwa_prior",
  "port_local_station_ids_used": ["KHWD01", "KHWD04", "KHWD05", "KHWD06", "KHWD07", "KHWD08"],
  "nearby_cwa_station_ids_used_for_current_prediction": [],
  "baseline_station_id": "467441",
  "baseline_station_used_for_current_prediction": false,
  "cwa_pop_prior_used": true
}
```

`no_realtime_khwd_mode=true`：

```json
{
  "selected_prediction_mode": "nearby_cwa_historical_model",
  "active_wind_source": "nearby_cwa_historical_model",
  "active_gust_source": "nearby_cwa_historical_model",
  "port_local_station_ids_used": [],
  "nearby_cwa_station_ids_used_for_current_prediction": ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"],
  "baseline_station_id": "467441",
  "baseline_station_used_for_current_prediction": false
}
```

## station_display_rows Rules

```text
KHWD used_for_current_prediction = true only when selected mode is port_local_postprocess or port_local_model
nearby CWA used_for_current_prediction = true only when selected mode is nearby_cwa_historical_model
467441 used_for_current_prediction = true only when selected mode is fallback_baseline
467441 is_port_local_core must always be false
nearby CWA is_port_local_core must always be false
```

## Reports

```text
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/training_orchestration_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_registry_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_manifest_validation_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/current_station_usage_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/ui_payload_snapshot.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/api_contract_snapshot_v34.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_selection_regression_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/rain_probability_integrity_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/station_role_violation_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/prediction_samples.json
```

## Acceptance

目前 v3.4 驗證結果：

```text
model_selection_regression failed_cases = 0
training_required = false
training_skipped = true
nearby_cwa_historical_model available = true
nearby_cwa_historical_model accepted = true
station_role_violations_found = false
rain_probability_preserved = true
```
