# Dispatch Risk API Contract v2.6

## Endpoint

```http
GET /api/v1/dispatch/risk?target_station_id=467441
```

回傳 `kaohsiung_port_dispatch_risk_v2.6` JSON。此 endpoint 不使用 v1 envelope，目的是讓前端直接取得派工風險 payload。

## Target 與 Input 語意

- `target_station_id=467441` 是高雄港派工風險輸出的 target/proxy。
- v2.6 不再把 467441 視為唯一輸入資料來源。
- input station pool 由 `kaohsiung_microclimate_lstm/config/station_pool.yaml` 決定。
- 多測站目前只作 postprocess，不進 LSTM model input。

## Request

| 參數 | 型別 | 預設 | 說明 |
| --- | --- | --- | --- |
| `target_station_id` | string | `467441` | 港區派工風險輸出 proxy |

## Response Top-Level Fields

| 欄位 | 說明 |
| --- | --- |
| `model_version` | 固定為 `kaohsiung_port_dispatch_risk_v2.6` |
| `generated_at` | 產生時間，Asia/Taipei |
| `target_area` | 港區與 target station metadata |
| `input_station_summary` | station pool 可用性與 fallback 狀態 |
| `forecast_anchors` | H1-H4 派工風險預測 |
| `cwa_forecast` | CWA PoP 對齊與 quality 結果 |
| `data_availability` | target、nearby、CWA、tide、visibility 可用性 |
| `reliability` | 各子模型與輔助資料可靠度 |
| `trace` | 模型資料流與安全語意 |

## input_station_summary

```json
{
  "target_station_id": "467441",
  "input_station_count": 4,
  "input_station_ids": ["467441", "C4Q01", "C4Q02", "C4P01", "COMC08"],
  "available_station_ids": ["467441", "C4Q01", "C4Q02"],
  "missing_station_ids": ["C4P01"],
  "multi_station_input": true,
  "fallback_to_single_station": false,
  "fallback_reason": null,
  "station_pool_mode": "port_local",
  "multi_station_feature_mode": "postprocess_only"
}
```

若只有 target station 可用：

```json
{
  "multi_station_input": false,
  "fallback_to_single_station": true,
  "fallback_reason": "Only target station data available."
}
```

## Anchor Fields

每個 `forecast_anchors[]` 包含：

- `rain.final_probability`
- `rain.level`
- `wind_speed.predicted_mps`
- `wind_speed.operation_level`
- `wind_speed.nearby_postprocess_applied`
- `wind_gust.predicted_mps`
- `wind_gust.operation_level`
- `wind_gust.nearby_postprocess_applied`
- `multi_station_postprocess`
- `dispatch_risk_level`
- `risk_trigger_detail`
- `dispatch_action_level`
- `dispatch_suggestion`

## Multi-Station Postprocess

目前只影響 H1/H2：

- `nearby_precipitation_1hr_max > 0.5`：rain probability 至少 0.70
- `nearby_precipitation_1hr_mean > 2.0`：rain probability 至少 0.85
- `nearby_rainy_station_count >= 2`：rain probability 至少 0.60
- `nearby_wind_speed_max >= wind_speed.warning`：H1/H2 wind level 至少 warning
- `nearby_wind_gust_max >= wind_gust.warning`：H1/H2 gust level 至少 warning

## Trace Requirements

```json
{
  "target_station_id": "467441",
  "target_station_role": "port_area_proxy",
  "multi_station_input": true,
  "input_station_count": 4,
  "input_station_ids": ["467441", "C4Q01", "C4Q02", "C4P01", "COMC08"],
  "nearby_station_count": 3,
  "fallback_to_single_station": false,
  "multi_station_feature_mode": "postprocess_only",
  "multi_station_features_used_as_model_input": false,
  "multi_station_features_used_as_postprocess": true,
  "train_inference_mismatch_prevented": true,
  "cwa_pop_used_as_model_input": false,
  "cwa_pop_quality_gate_enabled": true,
  "zero_pop_distinguished_from_missing": true,
  "normal_state_primary_trigger_none": true,
  "dispatch_risk_aggregation": "max_level_rule"
}
```

## Error Behavior

| 情境 | HTTP |
| --- | --- |
| target station CSV 不存在 | 404 |
| config 或模型推論失敗 | 503 |
| nearby station 缺資料 | 200，並寫入 `missing_station_ids` |
