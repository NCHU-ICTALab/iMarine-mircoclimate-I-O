# 高雄港微氣候派工風險 v3.4 總結

產出日期：2026-07-09

## 本版完成項目

- 將後端版本更新為 `kaohsiung_port_dispatch_risk_v3.4`。
- 新增 training orchestration CLI：`run_v34_training_orchestration.py`。
- 新增 model registry：`kaohsiung_microclimate_lstm/models/model_registry.json`。
- 新增 nearby CWA model manifest：`kaohsiung_microclimate_lstm/models/nearby_cwa_v34/model_manifest.json`。
- API 新增 `model_training_status`、`model_registry_summary`、`current_station_usage`、`station_display_rows`。
- API 新增：
  - `GET /api/v1/dispatch/model-status?target_area=KHH`
  - `GET /api/v1/dispatch/station-usage?target_area=KHH`

## 訓練狀態

目前系統已偵測到既有 nearby CWA historical model 已訓練且驗收通過，因此本版不重複訓練。

```json
{
  "training_checked": true,
  "training_required": false,
  "training_skipped": true,
  "skip_reason": "Existing accepted nearby CWA historical model found."
}
```

## 目前可用模型

- `port_local_model`：尚未訓練完成，未啟用。
- `nearby_cwa_historical_model`：已訓練、可用、驗收通過。
- `fallback_baseline`：保留作為最後 fallback，不作為港區核心測站。

## 實際選模結果

KHWD 港區即時資料可用時：

```json
{
  "prediction_mode": "port_local_postprocess",
  "active_wind_source": "KHWD",
  "active_gust_source": "KHWD",
  "baseline_station_used_for_current_prediction": false
}
```

模擬 `no_realtime_khwd_mode=true` 時：

```json
{
  "prediction_mode": "nearby_cwa_historical_model",
  "active_wind_source": "nearby_cwa_historical_model",
  "active_gust_source": "nearby_cwa_historical_model",
  "port_local_station_ids_used": [],
  "nearby_cwa_station_ids_used_for_current_prediction": [
    "C0V890",
    "C0V490",
    "C0V840",
    "C0V810",
    "C0V450",
    "C0V900"
  ],
  "baseline_station_used_for_current_prediction": false
}
```

## 保留的不變條件

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

## 驗證結果

- v3.4 指定測試：9 passed。
- 完整測試：139 passed。
- model selection regression：4/4 passed，failed_cases = 0。
- station role violation：未發現違規。
- rain probability integrity：保留 H1-H4 rain object 與 final probability。

## 報表位置

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
