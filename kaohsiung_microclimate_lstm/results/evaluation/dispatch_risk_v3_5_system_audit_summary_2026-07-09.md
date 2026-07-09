# 高雄港微氣候派工風險 v3.5 總結

產出日期：2026-07-09

## 本版完成項目

- 將後端版本更新為 `kaohsiung_port_dispatch_risk_v3.5`。
- 新增 System Audit builder：
  - `kaohsiung_microclimate_lstm/src/system_audit.py`
  - `kaohsiung_microclimate_lstm/src/tools/build_v35_system_audit_report.py`
- 新增 API：
  - `GET /api/v1/dispatch/system-audit?target_area=KHH`
- `dispatch/risk` 新增 `system_audit_summary`，讓前端知道可查詢完整 audit。
- demo 頁面新增 System Audit 區塊，顯示資料來源、資料期間、模型指標與測站角色。

## 不變條件

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

## 目前系統狀態

```text
normal_prediction_mode: port_local_postprocess
no_realtime_khwd_mode_selected: nearby_cwa_historical_model
nearby_cwa_historical_model_status: trained_available_accepted
port_local_model_status: disabled_dataset_not_ready
fallback_baseline_status: available_last_resort_only
```

## 資料來源盤點

- `KHWD`：港區即時 wind/gust 來源，正常模式目前有使用。
- `nearby_cwa_historical`：歷史 fallback model 訓練參考，不是 port-local core。
- `467441`：最後 fallback baseline only，不是核心測站。
- `CWA_PoP_Qianzhen`：雨量機率 prior only，不作 model input。

## 資料期間與筆數

目前 audit 讀到：

```text
KHWD realtime recent:
  total_rows: 12
  duration_days: 0.001

nearby CWA historical training:
  total_rows: 184614
  duration_days: 1282
  valid_ratio: 0.9988

fallback 467441:
  total_rows: 4144
  duration_days: 179.917
```

若後續缺少資料或無法解析時間欄位，v3.5 會回傳 `status: not_available` 與 `reason`，不會偽造 0 天或 0 筆。

## 模型指標

目前 nearby CWA historical model 指標：

```text
wind_speed H1 MAE: 0.5919 m/s
wind_gust H1 MAE: 0.6835 m/s
rain_probability H1 Brier Score: 0.0183
```

`wind_speed` / `wind_gust` 是 regression，v3.5 顯示誤差指標 MAE / RMSE / R2，不用 accuracy 描述。

## 產出報表

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

## 驗證結果

- v3.5 指定測試：8 passed。
- demo + v3.5 指定測試：9 passed。
- 完整測試：147 passed。
- `no_fabricated_metrics: true`
- `no_fabricated_dataset_duration: true`
- `station_inventory_loaded: true`
