# 高雄港微氣候派工風險後端系統規格 v2.6

## 版本

- project version：`v2.6`
- model version：`kaohsiung_port_dispatch_risk_v2.6`
- target station：`467441`
- target role：`port_area_proxy`
- multi-station feature mode：`postprocess_only`

## 設計原則

v2.6 將 467441 定義為高雄港派工風險輸出的 target/proxy，不再把它當作唯一輸入站。系統會透過 `config/station_pool.yaml` 載入高雄港周邊測站資料，建立 station pool 可用性摘要與 nearby aggregation features。

為避免 train-inference mismatch，v2.6 不把 multi-station aggregation features 餵入既有 LSTM 模型。多測站資訊只用於：

- H1/H2 降雨機率後處理
- H1/H2 風速風險後處理
- H1/H2 陣風風險後處理
- JSON trace / confidence / fallback 狀態揭露

## Station Pool

設定檔：

```text
kaohsiung_microclimate_lstm/config/station_pool.yaml
```

目前 station pool：

- `467441`
- `C4Q01`
- `C4Q02`
- `C4P01`
- `COMC08`

若附近測站缺資料，系統不可中斷；只要 target station 存在，就應回傳預測並在 `missing_station_ids` 中揭露。若只剩 target station，則：

```json
{
  "multi_station_input": false,
  "fallback_to_single_station": true,
  "fallback_reason": "Only target station data available."
}
```

## 新增模組

```text
src/data/multi_station_loader.py
src/data/nearby_aggregation.py
src/data/station_pool.py
```

主要職責：

- 讀取 station pool 設定。
- 載入 `data/raw/observed_hourly/{station_id}.csv`。
- 區分 available / missing station。
- 建立 nearby wind、gust、rain aggregation features。

## 預測入口

```python
predict_dispatch_risk_v26(
    target_station_id: str,
    recent_observations,
    nearby_observations=None,
    multi_station_observations=None,
    cwa_forecast=None,
    tide_observations=None,
    visibility_observations=None,
    config_path: str = "config.yaml",
)
```

流程：

1. 載入 config。
2. 載入或接收 station pool observations。
3. 建立 input station summary。
4. 建立 nearby aggregation features。
5. 沿用 v2.5.2 base model flow。
6. 套用 v2.6 nearby postprocess。
7. 重新計算 dispatch risk、trigger 與 action。
8. 回傳 v2.6 JSON。

## Postprocess Rules

只套用於 H1/H2：

| 條件 | 效果 |
| --- | --- |
| `nearby_precipitation_1hr_max > 0.5` | rain probability 至少 0.70 |
| `nearby_precipitation_1hr_mean > 2.0` | rain probability 至少 0.85 |
| `nearby_rainy_station_count >= 2` | rain probability 至少 0.60 |
| `nearby_wind_speed_max >= warning threshold` | wind operation level 至少 warning |
| `nearby_wind_gust_max >= warning threshold` | gust operation level 至少 warning |

## 必要 Trace

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
  "train_inference_mismatch_prevented": true
}
```

## 保留 v2.5.2 行為

v2.6 不改變以下邏輯：

- CWA PoP quality gate。
- 0% PoP 與 missing/null/parse error 的區分。
- CWA PoP 不作為模型 input。
- CWA prior 只用於 H3/H4。
- Beaufort scale。
- gust uncertainty buffer。
- normal risk 時 `primary_trigger = none`。
- dispatch action mapping。
- tide / visibility 目前不進 max risk。

## 測試

```powershell
python -m pytest tests/test_station_pool.py tests/test_multi_station_loader.py tests/test_nearby_aggregation.py tests/test_predict_dispatch_risk_v26.py tests/test_dispatch_risk_api_multistation.py --basetemp .tmp_pytest_v26
```
