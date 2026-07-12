# Dispatch Risk API Contract v2.8 / v2.8.1

最新版本：`kaohsiung_port_dispatch_risk_v2.8.1`

v2.8 新增 port-local data acquisition。v2.8.1 進一步修正 TWPort realtime parser，可解析 `KHWD01M01`、`KHWD01M10` 等 raw sensor id，並正規化為 canonical station id `KHWD01`。

## Endpoint

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
```

Legacy-compatible:

```text
GET /api/v1/dispatch/risk?target_station_id=467441
```

## v2.8.1 Parser Rules

- Canonical station ids: `KHWD01`, `KHWD04`, `KHWD05`, `KHWD06`, `KHWD07`, `KHWD08`
- Accepted raw sensor ids: `{station_id}M01`, `{station_id}M10`, and any raw id that starts with the canonical station id
- Extracted fields: `WS_AVG`, `WD_AVG`, `WS_MAX`, `WD_MAX`, `MAX_T`
- Same station with multiple records: latest timestamp wins; if tied, the more complete record wins
- Missing timestamp: output is allowed with `quality_flag=degraded`
- Missing gust: output is allowed with `quality_flag=missing_gust`

Canonical record example:

```json
{
  "station_id": "KHWD01",
  "station_type": "wind",
  "timestamp": "2026-06-02T13:54:00+08:00",
  "wind_speed": 3.336,
  "wind_direction": 282,
  "wind_gust": 6.53,
  "wind_gust_direction": 271,
  "raw_station_ref": "KHWD01M01",
  "source": "twport_realtime_panel"
}
```

## Trace Fields

```json
{
  "port_local_data_acquisition_enabled": true,
  "port_local_data_refresh_attempted": true,
  "port_local_data_refresh_success": true,
  "port_local_station_files_created": [
    "KHWD01.csv",
    "KHWD04.csv",
    "KHWD05.csv",
    "KHWD06.csv",
    "KHWD07.csv",
    "KHWD08.csv"
  ],
  "port_local_data_report_path": "results/port_local_data_v28/station_availability_report.json"
}
```

Existing station priority fields remain required:

- `station_priority_policy`
- `prediction_mode`
- `using_port_local_station`
- `fallback_to_467441`
- `467441_used_as_core_station`
- `467441_usage`

## Current Actual Result

After the v2.8.1 parser patch, the fetch tool successfully created:

```text
KHWD01.csv
KHWD04.csv
KHWD05.csv
KHWD06.csv
KHWD07.csv
KHWD08.csv
```

The API response is now:

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v2.8.1",
  "prediction_mode": "port_local_postprocess",
  "using_port_local_station": true,
  "fallback_to_467441": false,
  "467441_used_as_core_station": false
}
```
