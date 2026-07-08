# 高雄港微氣候派工風險 v2.5.1 CWA Quality Patch 摘要

日期：2026-07-08

## 實作重點

v2.5.1 針對 CWA PoP 品質判斷做補強，避免把 missing / null / parse error 誤判成 0%：

- 新增 `src/cwa/cwa_pop_quality.py`
- 新增 `predict_dispatch_risk_v251()`
- 每個 H1-H4 anchor 都輸出 `cwa_pop_quality`
- CWA prior 只在 quality valid 時套用
- raw `"0"` / `0` 會被視為有效 0%，不是 missing
- missing / null / parse_error / out_of_range 不會套用 CWA prior
- trace 新增：
  - `cwa_pop_quality_gate_enabled`
  - `zero_pop_distinguished_from_missing`

## CWA 實際抓取結果

本次重新解析 CWA source：

- dataset_id: `F-D0047-091`
- location_name: `前鎮區`
- element_name: `3小時降雨機率`
- source_resolution: `3h`
- record_count: `7`
- fetched_at: `2026-07-08T00:09:14+08:00`

輸出檔：

- `config/resolved_cwa_forecast_source.json`
- `results/dispatch_risk_v251/cwa_fetch_report.json`

## Anchor CWA Quality

本次 H1-H4 都有對齊到 CWA forecast period，raw value 都是 `"0"`，因此全部是 valid 0%。

| Anchor | matched | raw_value | normalized_value | parse_status | quality_status | prior applied |
|---|---|---:|---:|---|---|---|
| H1 | true | `"0"` | 0.0 | ok | valid | false |
| H2 | true | `"0"` | 0.0 | ok | valid | false |
| H3 | true | `"0"` | 0.0 | ok | valid | true |
| H4 | true | `"0"` | 0.0 | ok | valid | true |

H1/H2 不套用 prior 是因為設定只允許 H3/H4 套用；H3/H4 套用 0% prior，將雨量機率往下修正。

## 實際 v2.5.1 預測結果

輸出檔：

- `results/dispatch_risk_v251/prediction_samples.json`
- `results/dispatch_risk_v251/metrics.json`
- `results/dispatch_risk_v251/reliability_report.json`

| Anchor | rain final prob | CWA prior | dispatch risk | action | primary trigger |
|---|---:|---|---|---|---|
| H1 | 0.3463 | false | watch | observe_only | rain_probability |
| H2 | 0.2960 | false | normal | normal_dispatch | wind_gust |
| H3 | 0.1474 | true | normal | normal_dispatch | wind_gust |
| H4 | 0.1899 | true | normal | normal_dispatch | wind_gust |

## 測試

執行：

```bash
python -m pytest tests/test_cwa_pop_quality.py tests/test_cwa_anchor_alignment_quality.py tests/test_cwa_open_data_client.py tests/test_cwa_forecast_resolver.py tests/test_cwa_pop_prior.py tests/test_predict_dispatch_risk_v251.py tests/test_predict_dispatch_risk_v25.py tests/test_beaufort_scale.py tests/test_level_mapping.py tests/test_dispatch_risk_aggregator.py tests/test_risk_trigger_detail.py tests/test_action_mapping.py tests/test_rain_probability_rules.py tests/test_rain_probability_blender.py tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v251
```

結果：`31 passed`

## 結論

v2.5.1 已可清楚區分 CWA 0% 與 CWA missing。這版可避免後端或前端誤以為 `null` 是 0%，也能在每個 anchor 的 rain source detail 中追蹤 CWA prior 是否套用與套用原因。
