# Dispatch Risk API Contract v3.3

版本：`kaohsiung_port_dispatch_risk_v3.3`

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
GET /api/v1/dispatch/risk?target_area=KHH&no_realtime_khwd_mode=true
```

`no_realtime_khwd_mode=true` 只用於 regression / fallback scenario validation。它不刪除 KHWD CSV，也不修改資料，只讓本次 request 的 selection engine 視為 KHWD 即時資料不可用。

## Prediction Mode Chain

```text
port_local_model
port_local_postprocess
nearby_cwa_historical_model
fallback_baseline
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

## Normal Mode Result

KHWD 即時資料可用且 nearby CWA historical model accepted 時：

```json
{
  "prediction_mode": "port_local_postprocess",
  "fallback_to_nearby_cwa_historical_model": false,
  "fallback_to_467441": false
}
```

## no_realtime_khwd_mode Result

```json
{
  "prediction_mode": "nearby_cwa_historical_model",
  "fallback_to_nearby_cwa_historical_model": true,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false
}
```

## model_selection_summary

v3.3 必須包含：

```text
selected_mode
port_local_model_accepted
port_local_postprocess_available
nearby_cwa_historical_model_available
nearby_cwa_historical_model_accepted
fallback_to_nearby_cwa_historical_model
fallback_to_467441
selection_reason
fallback_chain
evaluated_modes
blocking_reasons
```

## trace

v3.3 必須包含：

```text
selection_engine_version = v3.3
selection_case_id
khwd_realtime_available
valid_khwd_station_count
no_realtime_khwd_mode
khwd_realtime_disabled_by_request
selection_assertions
```

## Reports

```text
results/dispatch_risk_v33/model_selection_regression_report.json
results/dispatch_risk_v33/scenario_validation_report.json
results/dispatch_risk_v33/api_contract_snapshot_v33.json
results/dispatch_risk_v33/rain_probability_integrity_report.json
results/dispatch_risk_v33/station_role_violation_report.json
results/dispatch_risk_v33/mode_transition_matrix.json
results/dispatch_risk_v33/prediction_samples.json
```
