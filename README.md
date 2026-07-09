# 高雄港微氣候派工風險 API

本專案提供高雄港周邊微氣候資料擷取、模型預測與派工風險 API。最新後端版本為 `kaohsiung_port_dispatch_risk_v3.5`。

## v3.5 重點

- 保留 v3.3 deterministic model selection：`port_local_model -> port_local_postprocess -> nearby_cwa_historical_model -> fallback_baseline`。
- 保留 v3.4 training orchestration、model registry、model manifest、station usage payload。
- 新增 System Audit：盤點資料來源、測站角色、資料期間、模型誤差指標與選模摘要。
- API 回傳 `system_audit_summary`，完整內容由 `/api/v1/dispatch/system-audit` 查詢。
- demo 頁面會顯示 System Audit cards、資料來源表、資料期間表、模型指標表與測站角色表。
- debug/admin 端點：
  - `GET /api/v1/dispatch/model-status?target_area=KHH`
  - `GET /api/v1/dispatch/station-usage?target_area=KHH`
  - `GET /api/v1/dispatch/system-audit?target_area=KHH`

目前正常 KHWD 可用時：

```json
{
  "prediction_mode": "port_local_postprocess",
  "active_wind_source": "KHWD",
  "active_gust_source": "KHWD",
  "training_required": false,
  "training_skipped": true
}
```

模擬 `no_realtime_khwd_mode=true` 時：

```json
{
  "prediction_mode": "nearby_cwa_historical_model",
  "active_wind_source": "nearby_cwa_historical_model",
  "active_gust_source": "nearby_cwa_historical_model",
  "baseline_station_used_for_current_prediction": false
}
```

## 不變條件

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

角色定義：

```text
KHWD = 港區即時核心測站
nearby CWA stations = historical fallback training reference
467441 = fallback baseline only
CWA PoP = rain prior only
```

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` 內可放 CWA Open Data API key，例如：

```text
CWA_API_KEY=your-cwa-open-data-key
```

請勿將真實 API key commit 到 Git。

## 啟動 API

```powershell
uvicorn app.api:app --reload
```

常用端點：

```text
GET /
GET /dispatch-risk-demo
GET /health
GET /docs
GET /api/v1/schema
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
GET /api/v1/dispatch/risk?target_area=KHH&no_realtime_khwd_mode=true
GET /api/v1/dispatch/model-status?target_area=KHH
GET /api/v1/dispatch/station-usage?target_area=KHH
GET /api/v1/dispatch/system-audit?target_area=KHH
GET /api/v1/microclimate/current
GET /api/v1/microclimate/forecast?minutes=90
```

## Port-local 資料抓取

```powershell
python kaohsiung_microclimate_lstm/src/tools/fetch_port_local_stations.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --station-pool kaohsiung_microclimate_lstm/config/station_pool.yaml `
  --output-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly `
  --report-dir kaohsiung_microclimate_lstm/results/port_local_data_v28
```

目前港區風力測站：

```text
KHWD01, KHWD04, KHWD05, KHWD06, KHWD07, KHWD08
```

## Nearby CWA Historical 訓練成果

已完成 nearby CWA/CODIS historical fallback model 訓練，使用比 `467441` 更接近高雄港的測站：

```text
C0V890, C0V490, C0V840, C0V810, C0V450, C0V900
```

主要成效：

```text
training_days: 1282
station_samples: 184614
wind_speed H1 MAE: 0.5919 m/s
wind_gust H1 MAE: 0.6835 m/s
rain H1 Brier Score: 0.0183
rain H1 AUC: 0.9638
critical_under_warning_count: 0
```

## v3.5 CLI

System audit：

```powershell
python kaohsiung_microclimate_lstm/src/tools/build_v35_system_audit_report.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --target-area KHH `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v35
```

## v3.4 CLI

Training orchestration：

```powershell
python kaohsiung_microclimate_lstm/src/tools/run_v34_training_orchestration.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --target-area KHH `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v34
```

Model selection regression：

```powershell
python kaohsiung_microclimate_lstm/src/tools/run_model_selection_regression.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v34
```

## v3.5 報表

```text
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/system_audit_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/data_source_inventory_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/station_inventory_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/dataset_duration_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_accuracy_summary_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_selection_summary_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/ui_dashboard_payload_v35.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/api_contract_snapshot_v35.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v35/prediction_samples_v35.json
```

## v3.4 報表

```text
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/training_orchestration_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_registry_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_manifest_validation_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/current_station_usage_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/ui_payload_snapshot.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/api_contract_snapshot_v34.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/model_selection_regression_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/rain_probability_integrity_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/station_role_violation_report.json
kaohsiung_microclimate_lstm/results/dispatch_risk_v34/prediction_samples.json
```

## 測試

```powershell
python -m pytest
```

v3.5 指定測試：

```powershell
python -m pytest tests/test_dispatch_risk_v35_system_audit.py tests/test_dispatch_risk_v35_dataset_duration.py tests/test_dispatch_risk_v35_model_accuracy_summary.py tests/test_dispatch_risk_v35_station_inventory.py tests/test_dispatch_risk_v35_ui_dashboard_payload.py --basetemp .tmp_pytest_v35
```

v3.4 指定測試：

```powershell
python -m pytest tests/test_dispatch_risk_v34_training_orchestration.py tests/test_dispatch_risk_v34_model_registry.py tests/test_dispatch_risk_v34_station_usage.py tests/test_dispatch_risk_v34_ui_payload.py tests/test_dispatch_risk_v34_api_contract.py --basetemp .tmp_pytest_v34
```

## 文件

- [v3.5 API Contract](docs/dispatch_risk_api_contract_v35.md)
- [v3.4 API Contract](docs/dispatch_risk_api_contract_v34.md)
- [v3.3 API Contract](docs/dispatch_risk_api_contract_v33.md)
- [v3.2 API Contract](docs/dispatch_risk_api_contract_v32.md)
- [v3.0 API Contract](docs/dispatch_risk_api_contract_v30.md)
- [v2.9 API Contract](docs/dispatch_risk_api_contract_v29.md)
- [v2.8 API Contract](docs/dispatch_risk_api_contract_v28.md)
- [v2.7 API Contract](docs/dispatch_risk_api_contract_v27.md)
- [v2.6 API Contract](docs/dispatch_risk_api_contract_v26.md)
