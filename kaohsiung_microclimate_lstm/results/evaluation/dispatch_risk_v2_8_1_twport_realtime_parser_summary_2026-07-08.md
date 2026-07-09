# Dispatch Risk v2.8.1 TWPort Realtime Parser Summary

Generated at: 2026-07-08T23:31:59

## Result

- model_version: `kaohsiung_port_dispatch_risk_v2.8.1`
- prediction_mode: `port_local_postprocess`
- using_port_local_station: `True`
- port_local_station_count: `6`
- port_local_station_ids: `['KHWD01', 'KHWD04', 'KHWD05', 'KHWD06', 'KHWD07', 'KHWD08']`
- fallback_to_467441: `False`
- 467441_used_as_core_station: `False`

## Fetch Outcome

The TWPort realtime parser now extracts KHWD raw sensor ids such as `KHWD01M01` and `KHWD01M10`, canonicalizes them to `KHWD01`, and writes canonical KHWD CSV files. Current available KHWD files: `KHWD01.csv`, `KHWD04.csv`, `KHWD05.csv`, `KHWD06.csv`, `KHWD07.csv`, `KHWD08.csv`.

## Forecast Anchors

- H1: risk `watch`, action `observe_only`, trigger `rain_probability`
- H2: risk `normal`, action `normal_dispatch`, trigger `none`
- H3: risk `normal`, action `normal_dispatch`, trigger `none`
- H4: risk `normal`, action `normal_dispatch`, trigger `none`
