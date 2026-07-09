# Dispatch Risk API Contract v2.9

版本：`kaohsiung_port_dispatch_risk_v2.9`

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
```

## Required Behavior

- `prediction_mode` should be `port_local_postprocess` when at least two valid KHWD stations are available.
- `fallback_to_467441` must be `false` in port-local mode.
- `467441_used_as_core_station` must always be `false`.
- KHWD data must be used only for port-local wind/gust postprocess validation, not as LSTM model input.
- Rain probability must be preserved in every forecast anchor.

## Required Anchor Fields

Each `forecast_anchors[]` item must include:

```text
rain
wind_speed
wind_gust
dispatch_risk_level
risk_trigger_detail
dispatch_action_level
```

Each `rain` object must include:

```text
raw_model_probability
nearby_adjusted_probability
port_local_adjusted_probability
cwa_adjusted_probability
final_probability
level
confidence
source_detail
```

## Required Trace Fields

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v2.9",
  "prediction_mode": "port_local_postprocess",
  "using_port_local_station": true,
  "port_local_wind_station_count": 6,
  "port_local_wind_postprocess_enabled": true,
  "port_local_gust_postprocess_enabled": true,
  "rain_probability_preserved": true,
  "rain_probability_model_used": true,
  "cwa_pop_prior_enabled": true,
  "cwa_pop_quality_gate_enabled": true,
  "dispatch_risk_uses_postprocessed_wind_gust": true,
  "467441_used_as_core_station": false
}
```

## Reports

```text
results/dispatch_risk_v29/prediction_samples.json
results/dispatch_risk_v29/port_local_postprocess_report.json
results/dispatch_risk_v29/rain_probability_report.json
results/dispatch_risk_v29/dispatch_risk_trace_report.json
```

## Current Actual Result

Current KHWD availability:

```text
KHWD01, KHWD04, KHWD05, KHWD06, KHWD07, KHWD08
```

Current API result:

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v2.9",
  "prediction_mode": "port_local_postprocess",
  "using_port_local_station": true,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false,
  "rain_probability_preserved": true
}
```
