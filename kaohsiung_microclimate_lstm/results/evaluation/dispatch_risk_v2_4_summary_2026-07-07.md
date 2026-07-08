# 高雄港微氣候派工風險 v2.4 實作摘要

日期：2026-07-07

## 實作內容

依照 v2.4 規格，這版將輸出從「雨量警示」擴充為「派工風險參考」：

- 新增 `kaohsiung_port_dispatch_risk_v2.4` 設定區塊。
- 新增 H1-H4（30/60/90/120 分鐘）派工風險輸出。
- 雨量改以 `rain_probability` 做等級判斷，不再把降雨量 mm regression 當派工主依據。
- 風速、陣風沿用既有 467441 `wind_speed_gust` 模型，再做門檻映射。
- 陣風套用保守 buffer：`gust_uncertainty_buffer_mps = 1.2`。
- CWA PoP 僅作為 postprocess prior，不進入模型 input。
- `dispatch_risk_level = max(rain_level, wind_level, gust_level, visibility_level, tide_level)`。
- visibility / tide 目前標記為 unavailable 或 reference_only，不納入最大風險計算。

## 新增檔案

- `src/risk/level_mapping.py`
- `src/risk/dispatch_risk_aggregator.py`
- `src/risk/confidence.py`
- `src/postprocess/cwa_pop_prior.py`
- `src/data/station_pool.py`
- `src/data/feature_builder.py`
- `src/data/label_builder.py`
- `tests/test_level_mapping.py`
- `tests/test_dispatch_risk_aggregator.py`
- `tests/test_cwa_pop_prior.py`
- `tests/test_feature_builder.py`
- `tests/test_predict_dispatch_risk_v24.py`

## 修改檔案

- `config.yaml`
- `src/predict.py`

## 實際預測範例

輸出檔：

- `results/dispatch_risk_v24/prediction_samples.json`
- `results/dispatch_risk_v24/metrics.json`

本次使用 467441 最新資料推論結果：

| Anchor | rain_probability | wind_speed m/s | wind_gust m/s | dispatch_risk_level |
|---|---:|---:|---:|---|
| H1 | 0.3463 | 1.352 | 4.149 | watch |
| H2 | 0.2960 | 1.218 | 3.433 | normal |
| H3 | 0.1843 | 1.063 | 3.346 | normal |
| H4 | 0.2374 | 1.537 | 3.361 | normal |

H1 為 `watch`，主要原因是雨量機率達 watch 門檻；風速與陣風皆未達風險門檻。

## 既有模型表現

467441 風速模型可作派工參考：

| Target | H1 MAE | H2 MAE | H3 MAE | H4 MAE | Grade |
|---|---:|---:|---:|---:|---|
| wind_speed | 0.534 | 0.537 | 0.588 | 0.578 | H1-H4 excellent |
| wind_gust | 1.221 | 1.137 | 1.223 | 1.196 | H1 acceptable, H2-H4 excellent |

雨量模型仍需保守使用：

| Anchor | MAE | RMSE | CSI > 1mm | FAR > 1mm | Grade |
|---|---:|---:|---:|---:|---|
| H1 | 1.632 mm | 5.189 mm | 0.110 | 0.835 | poor |
| H2 | 1.717 mm | 5.250 mm | 0.075 | 0.884 | poor |
| H3 | 1.409 mm | 5.067 mm | 0.148 | 0.733 | poor |
| H4 | 1.378 mm | 5.025 mm | 0.058 | 0.893 | poor |

因此 v2.4 將雨量定位為 `low_to_medium` reliability，風速為 `high`，陣風為 `medium_high`。

## Trace 檢查

本次輸出包含：

- `port_local_scope: true`
- `multi_station_input: true`
- `city_wide_forecast_as_target: false`
- `train_inference_mismatch_prevented: true`
- `cwa_pop_used_as_model_input: false`
- `cwa_pop_used_as_postprocess_prior: false`（本次 CWA PoP 無可用資料）
- `dispatch_risk_aggregation: max_level_rule`

## 測試

執行：

```bash
python -m pytest tests/test_level_mapping.py tests/test_dispatch_risk_aggregator.py tests/test_cwa_pop_prior.py tests/test_feature_builder.py tests/test_predict_dispatch_risk_v24.py tests/test_rain_probability_rules.py tests/test_rain_probability_blender.py tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v24
```

結果：`17 passed`

## 結論

v2.4 已可提供前端派工排程使用的風險參考 JSON。現階段最適合作為派工依據的是風速與陣風；雨量可作警戒提示，但不建議單獨作為停工或高風險判斷依據。
