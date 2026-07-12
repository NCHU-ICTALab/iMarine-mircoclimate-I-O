# Dispatch Risk API Contract v3.0

版本：`kaohsiung_port_dispatch_risk_v3.0`

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
```

## Selection Modes

v3.0 依序選擇：

```text
port_local_model -> port_local_postprocess -> fallback_baseline
```

`port_local_model` 只有在 dataset ready、模型已訓練、metrics 通過驗收且 critical under-warning 為 0 時才可使用。

## Required Top-level Fields

```text
model_version
prediction_mode
model_selection_summary
station_priority_summary
forecast_anchors
data_availability
trace
```

## model_selection_summary

```json
{
  "selected_mode": "port_local_postprocess",
  "dataset_ready": false,
  "port_local_model_trained": false,
  "port_local_model_accepted": false,
  "fallback_to_port_local_postprocess": true,
  "fallback_to_467441": false,
  "selection_reason": "Dataset readiness failed; using port-local postprocess.",
  "failed_reasons": [],
  "fallback_chain": [
    "port_local_model",
    "port_local_postprocess",
    "fallback_baseline"
  ]
}
```

## Required Trace Fields

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v3.0",
  "prediction_mode": "port_local_postprocess",
  "port_local_model_training_enabled": true,
  "port_local_model_selected": false,
  "port_local_model_accepted": false,
  "fallback_to_port_local_postprocess": true,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false,
  "rain_probability_preserved": true,
  "rain_model_mode": "existing_model_plus_cwa_prior",
  "cwa_pop_used_as_model_input": false,
  "cwa_pop_quality_gate_enabled": true
}
```

## Reports

```text
results/dispatch_risk_v30/dataset_readiness_report.json
results/dispatch_risk_v30/port_local_training_report.json
results/dispatch_risk_v30/port_local_model_metrics.json
results/dispatch_risk_v30/model_selection_report.json
results/dispatch_risk_v30/prediction_samples.json
results/dispatch_risk_v30/rain_probability_report.json
```

## Current Actual Result

目前 KHWD CSV 可用，但歷史訓練資料不足：

```json
{
  "prediction_mode": "port_local_postprocess",
  "dataset_ready": false,
  "port_local_model_trained": false,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false
}
```
