# I/O 合約

本文件定義後續模組應依賴的穩定介面。

## 版本

目前 schema：

```text
microclimate.v1
```

相容性規則：

- 既有 v1 欄位名稱與單位不可變更。
- 可新增非破壞性的 optional metadata。
- 破壞性變更必須建立新的 schema version。
- 下游模組應檢查 `schema_version`，並明確處理未知 major version。

## 穩定 Endpoints

```text
GET /api/v1/schema
GET /api/v1/microclimate/current
GET /api/v1/microclimate/forecast?minutes=90
GET /api/v1/cwa/history?hours=24&source=official_land
```

## Response Envelope

所有穩定 v1 endpoints 使用：

```json
{
  "schema_version": "microclimate.v1",
  "endpoint": "/api/v1/microclimate/current",
  "generated_at": "2026-07-02T18:45:00+08:00",
  "time_zone": "Asia/Taipei",
  "request": {},
  "metadata": {},
  "data_quality": {},
  "data": []
}
```

## Observation Record

`data` 中每筆 observation record 包含：

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `record_id` | string | 由來源、類型、測站、是否預報與觀測時間組成的穩定 ID |
| `source` | string | 正規化後的來源 ID |
| `device_type` | string | 正規化後的資料類型 |
| `station` | object | 測站識別與位置 |
| `time` | object | 觀測時間與抓取時間 |
| `metrics` | object | 正規化後的氣象/海象數值 |
| `quality` | object | 預報、新鮮度與信心等級資訊 |

## Metrics 單位

| 欄位 | 單位 |
| --- | --- |
| `wind_speed_mps` | m/s |
| `wind_gust_mps` | m/s |
| `wind_direction_deg` | 度 |
| `wind_gust_direction_deg` | 度 |
| `precipitation_10min_mm` | mm |
| `precipitation_1hr_mm` | mm |
| `precipitation_24hr_mm` | mm |
| `air_temperature_c` | 攝氏 |
| `relative_humidity_percent` | % |
| `air_pressure_hpa` | hPa，若來源有提供 |
| `visibility_m` | m |
| `tide_level` | 依 `tide_level_unit` 判斷 |
| `wave_height_m` | m |
| `wave_period_s` | 秒 |
| `wave_max_height_m` | m |
| `current_speed_mps` | m/s |
| `current_direction_deg` | 度 |

## 下游模組建議檢查

使用資料前建議：

1. 檢查 `schema_version`。
2. 檢查 `data_quality.contains_stale`。
3. 對 `quality.status_level` 為 `stale` 或 `outage` 的資料降權或忽略。
4. 即時港區條件優先採用 TWPort 現場觀測。
5. CWA 資料作為天氣補充；CWA 歷史 endpoints 用於需要歷史時間窗時即時查詢。

## 舊版 Endpoints

以下 endpoints 保留給人工檢查與相容用途：

```text
GET /microclimate/current
GET /microclimate/forecast?minutes=90
GET /microclimate/status
GET /cwa/history?hours=24&source=official_land
```

新下游模組不應依賴這些 endpoints 的精確輸出格式。
