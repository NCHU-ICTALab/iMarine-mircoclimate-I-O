# Dispatch Risk v2.8 Port-local Data Acquisition Summary

Generated at: 2026-07-08T23:22:58

## API Result

- model_version: `kaohsiung_port_dispatch_risk_v2.8`
- prediction_mode: `fallback_baseline`
- using_port_local_station: `False`
- fallback_to_467441: `True`
- 467441_used_as_core_station: `False`
- port_local_data_refresh_attempted: `True`
- port_local_data_refresh_success: `False`
- port_local_station_files_created: `[]`

## Port-local Fetch Status

The v2.8 fetch pipeline requested KHWD/KHTD/KHAW stations from TWPort. The current TWPort page did not return records whose station ids match the configured port-local ids, so no canonical KHWD/KHTD/KHAW CSV files were created.

Reports:

- `results/port_local_data_v28/fetch_report.json`
- `results/port_local_data_v28/quality_report.json`
- `results/port_local_data_v28/station_availability_report.json`
- `results/port_local_data_v28/normalization_report.json`

## Forecast Anchors

- H1: risk `watch`, action `observe_only`, trigger `rain_probability`
- H2: risk `normal`, action `normal_dispatch`, trigger `none`
- H3: risk `normal`, action `normal_dispatch`, trigger `none`
- H4: risk `normal`, action `normal_dispatch`, trigger `none`
