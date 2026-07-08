# 高雄港微氣候派工風險 v2.5.2 Risk Trigger Semantics Patch 摘要

日期：2026-07-08

## 實作重點

v2.5.2 修正 `risk_trigger_detail` 在 normal 狀態下的語意：

- 若 `dispatch_risk_level == normal`，`primary_trigger` 必須是 `none`
- normal 狀態不再依 trigger priority 回傳 `wind_gust`
- normal 狀態的 `primary_trigger_reliability` 為 `null`
- normal 狀態的 `dispatch_action_level` 固定為 `normal_dispatch`
- 非 normal 狀態仍依 priority 選 trigger：
  - `wind_gust > wind_speed > rain_probability > visibility > tide`

## 修改檔案

- `src/risk/risk_trigger_detail.py`
- `src/predict.py`
- `config.yaml`
- `tests/test_risk_trigger_detail.py`

新增測試：

- `tests/test_risk_trigger_semantics.py`
- `tests/test_predict_dispatch_risk_v252.py`

## 實際 v2.5.2 預測結果

輸出檔：

- `results/dispatch_risk_v252/prediction_samples.json`
- `results/dispatch_risk_v252/metrics.json`
- `results/dispatch_risk_v252/cwa_fetch_report.json`
- `results/dispatch_risk_v252/reliability_report.json`

| Anchor | dispatch risk | primary trigger | trigger reliability | action |
|---|---|---|---|---|
| H1 | watch | rain_probability | low_to_medium | observe_only |
| H2 | normal | none | null | normal_dispatch |
| H3 | normal | none | null | normal_dispatch |
| H4 | normal | none | null | normal_dispatch |

## Trace

v2.5.2 新增/確認：

- `normal_state_primary_trigger_none: true`
- `risk_trigger_semantics_patch_applied: true`

保留 v2.5.1：

- `cwa_pop_quality_gate_enabled: true`
- `zero_pop_distinguished_from_missing: true`
- `cwa_pop_used_as_model_input: false`

## 測試

執行：

```bash
python -m pytest tests/test_risk_trigger_semantics.py tests/test_risk_trigger_detail.py tests/test_action_mapping.py tests/test_predict_dispatch_risk_v252.py tests/test_predict_dispatch_risk_v251.py tests/test_cwa_pop_quality.py tests/test_cwa_anchor_alignment_quality.py tests/test_cwa_pop_prior.py tests/test_beaufort_scale.py tests/test_level_mapping.py tests/test_dispatch_risk_aggregator.py --basetemp .tmp_pytest_v252
```

結果：`26 passed`

## 結論

v2.5.2 已修正 normal 風險狀態的 trigger 語意。前端現在可以用 `primary_trigger: none` 判斷「沒有實際風險觸發因子」，不會再把正常狀態誤解為陣風觸發。
