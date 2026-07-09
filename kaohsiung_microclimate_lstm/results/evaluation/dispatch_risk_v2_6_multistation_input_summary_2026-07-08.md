# v2.6 Multi-Station Input Integration Summary

## 版本

- model version：`kaohsiung_port_dispatch_risk_v2.6`
- target station / proxy：`467441`
- station pool mode：`port_local`
- multi-station feature mode：`postprocess_only`
- generated date：`2026-07-08`

## 實作重點

v2.6 將 `467441` 明確定義為高雄港派工風險輸出的 target/proxy，不再把它視為唯一輸入站。API 會讀取 `config/station_pool.yaml`，載入 station pool 中可用測站，建立多測站可用性摘要與 nearby aggregation features。

目前多測站特徵只用於 postprocess，不進 LSTM model input：

```json
{
  "multi_station_features_used_as_model_input": false,
  "multi_station_features_used_as_postprocess": true,
  "train_inference_mismatch_prevented": true
}
```

## 實際 API 執行結果

`GET /api/v1/dispatch/risk?target_station_id=467441`

```json
{
  "model_version": "kaohsiung_port_dispatch_risk_v2.6",
  "input_station_count": 5,
  "available_station_ids": ["467441", "C4Q01", "C4Q02", "C4P01", "COMC08"],
  "missing_station_ids": [],
  "multi_station_input": true,
  "fallback_to_single_station": false
}
```

## 派工風險摘要

| Anchor | dispatch risk | action | 說明 |
| --- | --- | --- | --- |
| H1 | watch | observe_only | 由降雨機率觸發，可靠度 low_to_medium |
| H2 | normal | normal_dispatch | 無主要觸發因子 |
| H3 | normal | normal_dispatch | 無主要觸發因子 |
| H4 | normal | normal_dispatch | 無主要觸發因子 |

目前這次實跑中，nearby postprocess 沒有把 H1/H2 升級到更高風險；但輸出已包含每個 anchor 的 `multi_station_postprocess` trace，可供前端與後續除錯使用。

## 產出檔案

```text
results/dispatch_risk_v26/prediction_samples.json
results/dispatch_risk_v26/metrics.json
results/dispatch_risk_v26/cwa_fetch_report.json
results/dispatch_risk_v26/reliability_report.json
```

## 測試

v2.6 相關測試：

```text
tests/test_station_pool.py
tests/test_multi_station_loader.py
tests/test_nearby_aggregation.py
tests/test_predict_dispatch_risk_v26.py
tests/test_dispatch_risk_api_multistation.py
```
