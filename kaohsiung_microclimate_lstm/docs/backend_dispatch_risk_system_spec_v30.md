# 高雄港微氣候派工風險後端 v3.0

## 目的

v3.0 在 v2.9 `port_local_postprocess` 基礎上加入 port-local model training 與 fallback model selection。系統不再只宣告未來可訓練，而是具備資料集建置、readiness 檢查、baseline 訓練、metrics 驗收與 API 選模追蹤。

## API

- endpoint：`GET /api/v1/dispatch/risk?target_area=KHH`
- model version：`kaohsiung_port_dispatch_risk_v3.0`
- 預測入口：`predict_dispatch_risk_v30`

## 選模順序

```text
port_local_model -> port_local_postprocess -> fallback_baseline
```

目前實際資料不足，所以選用 `port_local_postprocess`。

## v3.0 新增模組

```text
src/data/port_local_training_dataset.py
src/data/dataset_readiness.py
src/training/train_port_local_model.py
src/model_selection/port_local_model_selector.py
src/tools/build_port_local_training_dataset.py
src/tools/train_port_local_model.py
```

## 實際結果

截至本次執行：

- sample_count：3
- training_days：0.001
- dataset_ready：false
- port_local_model_trained：false
- selected_mode：`port_local_postprocess`
- fallback_to_467441：false
- rain_probability_preserved：true

## 報表

```text
results/dispatch_risk_v30/dataset_readiness_report.json
results/dispatch_risk_v30/port_local_training_report.json
results/dispatch_risk_v30/port_local_model_metrics.json
results/dispatch_risk_v30/model_selection_report.json
results/dispatch_risk_v30/prediction_samples.json
results/dispatch_risk_v30/rain_probability_report.json
```
