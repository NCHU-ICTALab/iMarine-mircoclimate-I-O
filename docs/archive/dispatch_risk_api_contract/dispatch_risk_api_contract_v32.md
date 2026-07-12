# Dispatch Risk API Contract v3.2

版本：`kaohsiung_port_dispatch_risk_v3.2`

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
```

## Prediction Mode Selection

v3.2 的 fallback chain：

```text
port_local_model
port_local_postprocess
nearby_cwa_historical_model
fallback_baseline
```

當 KHWD 即時資料可用時，即使 nearby CWA historical model 已訓練並通過驗收，API 仍優先使用 `port_local_postprocess`。

## nearby_cwa_historical_summary

```json
{
  "enabled": true,
  "model_available": true,
  "model_accepted": true,
  "selected_station_ids": [
    "C0V890",
    "C0V490",
    "C0V840",
    "C0V810",
    "C0V450",
    "C0V900"
  ],
  "all_selected_stations_closer_than_467441": true,
  "baseline_station_id": "467441",
  "usage": "fallback_training_reference",
  "is_port_local_core": false
}
```

## Required Trace Fields

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v3.2",
  "prediction_mode": "port_local_postprocess",
  "nearby_cwa_historical_training_enabled": true,
  "nearby_cwa_historical_model_available": true,
  "nearby_cwa_historical_model_accepted": true,
  "nearby_cwa_selected_station_ids": ["C0V890", "C0V490", "C0V840", "C0V810", "C0V450", "C0V900"],
  "all_nearby_cwa_stations_closer_than_467441": true,
  "nearby_cwa_used_as_port_local_core": false,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false,
  "rain_probability_preserved": true,
  "rain_model_mode": "nearby_cwa_historical_rain_model_plus_cwa_prior",
  "cwa_pop_used_as_model_input": false
}
```

## Reports

```text
results/dispatch_risk_v32/nearby_station_ranking_report.json
results/dispatch_risk_v32/nearby_cwa_backfill_report.json
results/dispatch_risk_v32/nearby_cwa_readiness_report.json
results/dispatch_risk_v32/nearby_cwa_training_dataset_report.json
results/dispatch_risk_v32/nearby_cwa_model_metrics.json
results/dispatch_risk_v32/nearby_cwa_rain_probability_metrics.json
results/dispatch_risk_v32/model_selection_report.json
results/dispatch_risk_v32/prediction_samples.json
```

## Current Actual Result

```json
{
  "prediction_mode": "port_local_postprocess",
  "nearby_cwa_historical_model_available": true,
  "nearby_cwa_historical_model_accepted": true,
  "fallback_to_nearby_cwa_historical_model": false,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false
}
```
