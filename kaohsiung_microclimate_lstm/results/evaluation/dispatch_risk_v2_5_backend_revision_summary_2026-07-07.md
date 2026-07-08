# 高雄港微氣候派工風險 v2.5 後端修正版摘要

日期：2026-07-07

## 實作重點

v2.5 延續 v2.4 的派工風險 JSON，補強後端可解釋性與 CWA 抓取流程：

- 新增 `predict_dispatch_risk_v25()`。
- 風速與陣風輸出新增 Beaufort scale、中文風級、operation level、operation label。
- 陣風保留 1.2 m/s conservative buffer，並輸出 `buffer_applied` 與 `original_level_without_buffer`。
- 雨量輸出拆成 `raw_model_probability`、`nearby_adjusted_probability`、`cwa_adjusted_probability`、`final_probability`。
- CWA PoP 改由 `cwa_open_data` client 抓取，並只作 postprocess prior，不進模型 input。
- 新增 `risk_trigger_detail`，標示每個 anchor 的主要風險來源。
- 新增 `dispatch_action_level`，依風險等級與 primary trigger reliability 轉成派工行動層級。

## 新增與修改檔案

- `src/cwa/cwa_open_data_client.py`
- `src/tools/resolve_cwa_forecast_source.py`
- `src/risk/beaufort_scale.py`
- `src/risk/risk_trigger_detail.py`
- `src/risk/action_mapping.py`
- `src/risk/level_mapping.py`
- `src/postprocess/cwa_pop_prior.py`
- `src/cwa/location_resolver.py`
- `src/predict.py`
- `config.yaml`

新增測試：

- `tests/test_beaufort_scale.py`
- `tests/test_cwa_open_data_client.py`
- `tests/test_cwa_forecast_resolver.py`
- `tests/test_risk_trigger_detail.py`
- `tests/test_action_mapping.py`
- `tests/test_predict_dispatch_risk_v25.py`

## CWA 抓取結果

已使用專案內 `CWA_API_KEY` 實際抓取 CWA OpenData。

解析到的 forecast source：

- dataset_id: `F-D0047-091`
- location_name: `前鎮區`
- element_name: `3小時降雨機率`
- source_resolution: `3h`
- record_count: `7`
- fetched_at: `2026-07-07T23:27:10+08:00`

輸出檔：

- `config/resolved_cwa_forecast_source.json`
- `results/dispatch_risk_v25/cwa_fetch_report.json`

本次 anchor PoP：

| Anchor | CWA PoP |
| ------ | ------: |
| H1     |    null |
| H2     |     0.0 |
| H3     |     0.0 |
| H4     |     0.0 |

因此 CWA prior 對 H3/H4 有套用，但因 PoP 為 0.0，會把雨量機率往下修正。

## 實際 v2.5 預測結果

輸出檔：

- `results/dispatch_risk_v25/prediction_samples.json`
- `results/dispatch_risk_v25/metrics.json`
- `results/dispatch_risk_v25/reliability_report.json`

使用 467441 最新資料推論：

| Anchor | rain final prob | wind speed | wind Beaufort |      gust | gust Beaufort | dispatch risk | action          |
| ------ | --------------: | ---------: | ------------: | --------: | ------------: | ------------- | --------------- |
| H1     |          0.3463 |  1.352 m/s |             1 | 4.149 m/s |             3 | watch         | observe_only    |
| H2     |          0.2960 |  1.218 m/s |             1 | 3.433 m/s |             3 | normal        | normal_dispatch |
| H3     |          0.1474 |  1.063 m/s |             1 | 3.346 m/s |             2 | normal        | normal_dispatch |
| H4     |          0.1899 |  1.537 m/s |             1 | 3.361 m/s |             2 | normal        | normal_dispatch |

H1 為 `watch`，primary trigger 是 `rain_probability`，但雨量 reliability 為 `low_to_medium`，所以 action 降為 `observe_only`。

## Trace

本次 v2.5 輸出包含：

- `port_local_scope: true`
- `multi_station_input: true`
- `city_wide_forecast_as_target: false`
- `train_inference_mismatch_prevented: true`
- `cwa_pop_used_as_model_input: false`
- `cwa_pop_used_as_postprocess_prior: true`
- `dispatch_risk_aggregation: max_level_rule`

## 測試

執行：

```bash
python -m pytest tests/test_beaufort_scale.py tests/test_level_mapping.py tests/test_dispatch_risk_aggregator.py tests/test_cwa_open_data_client.py tests/test_cwa_forecast_resolver.py tests/test_cwa_pop_prior.py tests/test_risk_trigger_detail.py tests/test_action_mapping.py tests/test_predict_dispatch_risk_v25.py tests/test_predict_dispatch_risk_v24.py tests/test_rain_probability_rules.py tests/test_rain_probability_blender.py tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v25
```

結果：`25 passed`

## 結論

v2.5 已可作為前端派工排程介面的後端 JSON。相較 v2.4，這版更適合實際串接，因為每個 anchor 都能看到風級、操作等級、雨量來源細節、風險觸發因子與派工行動建議。

目前可靠度判斷仍維持：風速最高、陣風次之、雨量僅適合作警戒提示。
