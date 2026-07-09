# Dispatch Risk API Contract v2.7

版本：`kaohsiung_port_dispatch_risk_v2.7`

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
```

Legacy-compatible:

```text
GET /api/v1/dispatch/risk?target_station_id=467441
```

`target_station_id=467441` is accepted only as a legacy proxy. The response trace must identify it as fallback/baseline, not as a port-local core station.

## Station Priority Policy

The API uses `port_local_first` station priority:

1. Port-local TWPort stations: `KHWD/KHTD/KHAW`
2. CWA forecast auxiliary data such as Qianzhen PoP3h
3. `467441` fallback baseline
4. Reference-only stations such as `C4Q01`, `C4Q02`, `C4P01`, `COMC08`

`467441` must always be represented as:

```json
{
  "station_id": "467441",
  "role": "fallback_baseline",
  "is_port_local": false,
  "is_core_station": false,
  "usage": "fallback_only"
}
```

## Required Response Fields

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v2.7",
  "target_area": {
    "name": "Kaohsiung Port",
    "port_code": "KHH",
    "target_mode": "port_area"
  },
  "station_priority_summary": {},
  "forecast_anchors": [],
  "cwa_forecast": {},
  "data_availability": {},
  "reliability": {},
  "trace": {}
}
```

## station_priority_summary

```json
{
  "prediction_mode": "fallback_baseline",
  "target_area": "KHH",
  "using_port_local_station": false,
  "port_local_station_count": 0,
  "port_local_station_ids": [],
  "core_station_group": null,
  "fallback_to_467441": true,
  "fallback_station_id": "467441",
  "fallback_reason": "No valid port-local KHWD station data available.",
  "port_local_model_available": false,
  "model_retraining_required": true,
  "station_priority_policy": "port_local_first",
  "467441_used_as_core_station": false,
  "467441_usage": "fallback_baseline"
}
```

## trace

`trace` must include:

- `port_local_scope`
- `target_area`
- `station_priority_policy`
- `using_port_local_station`
- `port_local_station_count`
- `port_local_station_ids`
- `fallback_to_467441`
- `fallback_reason`
- `467441_used_as_core_station`
- `467441_usage`
- `prediction_mode`
- `port_local_model_available`
- `model_retraining_required`

When the legacy parameter is used, `trace` must also include:

```json
{
  "target_station_id_parameter_received": "467441",
  "target_station_id_treated_as": "fallback_baseline_or_legacy_proxy",
  "preferred_target_area": "KHH"
}
```

## Current Data Status

As of the generated v2.7 results, the local raw data directory does not contain `KHWD/KHTD/KHAW` observation files. Therefore the actual response uses `fallback_baseline`, with `467441_used_as_core_station=false`.
