# Dispatch Risk v2.7 Port-local Station Priority Summary

Generated at: 2026-07-08T23:04:35

## Result

- model_version: `kaohsiung_port_dispatch_risk_v2.7`
- prediction_mode: `fallback_baseline`
- target_area: `KHH`
- using_port_local_station: `False`
- port_local_station_count: `0`
- fallback_to_467441: `True`
- fallback_reason: `No valid port-local KHWD station data available.`
- 467441_used_as_core_station: `False`

## Available Raw Station Files

- `1786.csv`
- `46714D.csv`
- `467441.csv`
- `C4P01.csv`
- `C4Q01.csv`
- `C4Q02.csv`
- `COMC08.csv`

## Port-local Station Status

Configured port-local stations: KHWD01, KHWD04, KHWD05, KHWD06, KHWD07, KHWD08, KHTD01, KHTD04, KHTD05, KHAW01, KHAW07, KHAW08, KHAW09

Missing port-local stations: KHWD01, KHWD04, KHWD05, KHWD06, KHWD07, KHWD08, KHTD01, KHTD04, KHTD05, KHAW01, KHAW07, KHAW08, KHAW09

Current project data does not include KHWD/KHTD/KHAW observation files, so v2.7 correctly degrades to `fallback_baseline`. The fallback uses `467441` only as a baseline source and reports `467441_used_as_core_station=false`.

## Forecast Anchors

- H1: risk `watch`, action `observe_only`, trigger `rain_probability`
- H2: risk `normal`, action `normal_dispatch`, trigger `none`
- H3: risk `normal`, action `normal_dispatch`, trigger `none`
- H4: risk `normal`, action `normal_dispatch`, trigger `none`
