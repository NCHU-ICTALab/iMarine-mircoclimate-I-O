# 高雄港微氣候 LSTM 與派工風險後端

此資料夾包含微氣候模型、資料前處理、港區測站整合、派工風險推論、model registry 與 training orchestration。

## 目前版本

- API model version：`kaohsiung_port_dispatch_risk_v1.3`
- API endpoint：`GET /api/v1/dispatch/risk?target_area=KHH`
- 主要預測入口：`kaohsiung_microclimate_lstm.src.predict.predict_dispatch_risk_current`
- 選模引擎：`kaohsiung_microclimate_lstm.src.selection.model_selection_engine.select_prediction_mode`
- Training orchestration：`kaohsiung_microclimate_lstm.src.training_orchestration.run_training_orchestration`

## v1.3 System Audit

v1.3 延續系統盤點，用於前端 dashboard 顯示目前資料來源、測站角色、資料期間、模型指標與選模狀態。

```text
GET /api/v1/dispatch/system-audit?target_area=KHH
```

CLI：

```powershell
python kaohsiung_microclimate_lstm/src/tools/build_v35_system_audit_report.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --target-area KHH `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v35
```

## 目前選模流程

```text
port_local_model
  -> port_local_postprocess
  -> nearby_cwa_historical_model
  -> fallback_baseline
```

正常情境下，若 KHWD 港區即時風力資料可用，API 選擇 `port_local_postprocess`。當 request 帶入 `no_realtime_khwd_mode=true` 時，只在本次 selection engine 內模擬 KHWD 不可用；若 nearby CWA historical model 已訓練且驗收通過，會選擇 `nearby_cwa_historical_model`。

## v3.4 新增輸出

API response 會包含：

```text
model_training_status
model_registry_summary
current_station_usage
station_display_rows
```

這些欄位可供前端顯示目前 prediction mode、模型訓練狀態、目前使用測站、測站角色與 fallback 狀態。

## 不變條件

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

## Python 使用範例

```python
from pathlib import Path

from kaohsiung_microclimate_lstm.src.preprocess import load_observations
from kaohsiung_microclimate_lstm.src.predict import predict_dispatch_risk_current

project = Path("kaohsiung_microclimate_lstm")
df = load_observations(project / "data/raw/observed_hourly/467441.csv")

result = predict_dispatch_risk_current(
    fallback_observations=df,
    config_path=str(project / "config.yaml"),
    project_root=project,
    target_area="KHH",
    no_realtime_khwd_mode=False,
)
```

## Training Orchestration

```powershell
python kaohsiung_microclimate_lstm/src/tools/run_v34_training_orchestration.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --target-area KHH `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v34
```

目前狀態：

```text
training_checked: true
training_required: false
training_skipped: true
nearby_cwa_historical_model: trained / available / accepted
port_local_model: not trained / not accepted
```

## Nearby CWA Historical 訓練成果

使用測站：

```text
C0V890, C0V490, C0V840, C0V810, C0V450, C0V900
```

主要結果（2026-07-11 資料源頭缺值代碼污染清除、雨量回歸改採 log1p 目標轉換後重訓）：

```text
training_days: 1282
station_samples: 184614
wind_speed H1 MAE: 0.5512 m/s (R2 0.7625)
wind_gust H1 MAE: 0.6809 m/s (R2 0.8542)
rain H1 Brier Score: 0.0183
rain H1 AUC: 0.9546
critical_under_warning_count: 0
```

詳見 `docs/spec_v13_implementation_summary.md` 與規格書第 15 節的完整清理/評估紀錄。

## v1.3 報表

```text
results/dispatch_risk_v35/system_audit_report.json
results/dispatch_risk_v35/data_source_inventory_report.json
results/dispatch_risk_v35/station_inventory_report.json
results/dispatch_risk_v35/dataset_duration_report.json
results/dispatch_risk_v35/model_accuracy_summary_report.json
results/dispatch_risk_v35/model_selection_summary_report.json
results/dispatch_risk_v35/ui_dashboard_payload_v35.json
results/dispatch_risk_v35/api_contract_snapshot_v35.json
results/dispatch_risk_v35/prediction_samples_v35.json
```

## v3.4 報表

```text
results/dispatch_risk_v34/training_orchestration_report.json
results/dispatch_risk_v34/model_registry_report.json
results/dispatch_risk_v34/model_manifest_validation_report.json
results/dispatch_risk_v34/current_station_usage_report.json
results/dispatch_risk_v34/ui_payload_snapshot.json
results/dispatch_risk_v34/api_contract_snapshot_v34.json
results/dispatch_risk_v34/model_selection_regression_report.json
results/dispatch_risk_v34/rain_probability_integrity_report.json
results/dispatch_risk_v34/station_role_violation_report.json
results/dispatch_risk_v34/prediction_samples.json
```

## 測試

```powershell
python -m pytest
```

v1.3 指定測試：

```powershell
python -m pytest tests/test_dispatch_risk_v35_system_audit.py tests/test_dispatch_risk_v35_dataset_duration.py tests/test_dispatch_risk_v35_model_accuracy_summary.py tests/test_dispatch_risk_v35_station_inventory.py tests/test_dispatch_risk_v35_ui_dashboard_payload.py --basetemp .tmp_pytest_v35
```

v3.4 指定測試：

```powershell
python -m pytest tests/test_dispatch_risk_v34_training_orchestration.py tests/test_dispatch_risk_v34_model_registry.py tests/test_dispatch_risk_v34_station_usage.py tests/test_dispatch_risk_v34_ui_payload.py tests/test_dispatch_risk_v34_api_contract.py --basetemp .tmp_pytest_v34
```
