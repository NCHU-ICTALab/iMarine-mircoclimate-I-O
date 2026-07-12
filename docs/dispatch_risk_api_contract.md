# Dispatch Risk API Contract

Current external specification version: `v1.3`.

Current runtime model version is read from `kaohsiung_microclimate_lstm/config.yaml::project.model_version`.

Historical snapshots are archived under `docs/archive/dispatch_risk_api_contract/`. Internal implementation names such as `predict_dispatch_risk_v35` and `results/dispatch_risk_v35/` remain as audit-trace identifiers, not external specification versions.

## Version History

- v1.3 current: external model/spec version strings are consolidated on v1.3; `predict_dispatch_risk_current()` is the version-neutral entrypoint; historical contract snapshots are archived.
- Internal v35: system audit, data source/station/dataset duration summaries, model accuracy/selection reports, dashboard payload, CWA +3h/+6h display windows, wind/gust source switch, KHWD persistence blending, runtime live-cache reports, and model registry alignment.
- Internal v34: model registry and training orchestration checks for nearby CWA historical models.
- Internal v33: model-selection API contract, station role checks, rain probability integrity checks, and no-realtime KHWD scenario reporting.
- Internal v32: prediction-mode selection between port-local postprocess, nearby CWA historical model, and fallback baseline.
- Internal v30: port-local model readiness and model-selection report scaffolding.
- Internal v29: port-local wind postprocess, rain probability report, and prediction sample reporting.
- Internal v28: port-local station fetch, normalization, quality, and availability reports.
- Internal v27: dispatch-risk API multi-station and port-local refresh integration.
- Internal v26: dispatch-risk API refinements after the v25 rain/wind postprocess path.
- Internal v25 and earlier: H1-H4 dispatch-risk anchors, CWA PoP prior postprocess, risk trigger semantics, and early smoke coverage.

Policy: future API contract changes update this file and add one bullet here. Do not create new `dispatch_risk_api_contract_vNN.md` files unless a deliberately frozen audit snapshot is required.

## 版本定位

本文件是現行 v1.3 對外 API 契約。其內容延續內部 v35 實作階段的系統盤點與派工風險輸出對齊成果；內部 v35 名稱只作稽核追溯，不作對外規格版本。

## Endpoints

```text
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/risk?target_area=KHH&no_realtime_khwd_mode=true
GET /api/v1/dispatch/model-status?target_area=KHH
GET /api/v1/dispatch/station-usage?target_area=KHH
GET /api/v1/dispatch/system-audit?target_area=KHH
```

## Required Invariants

```json
{
  "467441_used_as_core_station": false,
  "nearby_cwa_used_as_port_local_core": false,
  "cwa_pop_used_as_model_input": false,
  "rain_probability_preserved": true
}
```

## Dispatch Risk Response

`GET /api/v1/dispatch/risk?target_area=KHH` 必須保留：

```text
model_version
generated_at
target_area
prediction_mode
forecast_anchors
extended_forecast_windows
cwa
data_availability
reliability
station_priority_summary
model_selection_summary
current_station_usage
station_display_rows
trace
```

### H1-H4 Nowcast

`forecast_anchors` 維持 H1~H4（30/60/90/120 分鐘）短期派工視窗，來源可為 `port_local_postprocess`、`nearby_cwa_historical_model` 或最後備援，不得混入 +3h/+6h 官方預報。

變數顯示層使用氣象或官方術語：

- 降雨量：`rain.amount_level` 回傳 `無`、`小雨`、`大雨`、`豪雨`、`大豪雨` 或 `not_applicable`。
- 風速：顯示 `wind_speed.beaufort.label_zh`，顏色仍由 `wind_speed.operation_level` 決定。
- 陣風：顯示 `wind_gust.beaufort.label_zh`，顏色仍由 `wind_gust.operation_level` 決定。
- 若港區即時後處理覆寫風速或陣風，demo 頁面顯示「觸發港區即時安全門檻」作為客觀說明。

港區即時安全門檻覆寫後，`wind_speed` 與 `wind_gust` 必須維持欄位一致性：

```text
operation_label == OPERATION_LABELS[operation_level]
port_local_postprocess_applied == port_local_postprocess.applied
```

此一致性已用 `GET /api/v1/dispatch/risk?target_area=KHH` 實際驗證：H1/H2 風速覆寫為 `stop`、陣風覆寫為 `high_risk` 時，label 與扁平 applied 欄位皆同步。

覆寫後 `beaufort` 也必須同步使用觸發安全門檻的 KHWD 即時值換算，不得停留在模型原始 `predicted_mps` 的蒲福級。未觸發覆寫的 H3/H4 維持使用模型原始預測換算。

### CWA PoP Prior Source

H1-H4 降雨機率後處理使用 CWA Open Data 目前 resolved source。此 source 必須：

- 優先使用 `F-D0047-065` 的 `3小時降雨機率`。
- `source_resolution` 由實際 `start_time` / `end_time` 時間差判斷，不可只看元素名稱。
- `config/resolved_cwa_forecast_source.json` 超過 `cwa_open_data.resolved_source_max_age_hours` 時需重新解析並覆寫。

目前驗證狀態：

```text
dataset_id: F-D0047-065
location_name: 前鎮區
element_name: 3小時降雨機率
source_resolution: 3h
valid_times: 32
```

### CWA +3h/+6h Official Windows

`extended_forecast_windows` 是獨立欄位，不屬於 H1~H4 模型外插。資料來源為 CWA `F-D0047-065`，降雨機率使用 `3小時降雨機率`，風速以官方蒲福風級區間呈現，不提供精確 m/s。

```json
{
  "available": true,
  "source": "cwa_official_forecast",
  "data_id": "F-D0047-065",
  "location_name": "前鎮區",
  "windows": [
    {
      "window": "+3h",
      "offset_minutes": 180,
      "source": "cwa_official_forecast",
      "wind_speed": {
        "available": true,
        "value_mps": null,
        "beaufort_scale_min": 6,
        "beaufort_scale_text": ">= 6",
        "wind_speed_text": ">= 11",
        "operation_level": "warning",
        "basis": "cwa_beaufort_scale_range_not_precise_value"
      },
      "rain_probability": {"available": true, "value": 0.1, "level": "normal"},
      "wind_gust": {"available": false, "reason": "no_official_cwa_gust_product"},
      "visibility": {"available": false, "reason": "no_official_cwa_visibility_product"}
    }
  ]
}
```

Frontend 相容簡化欄位 `cwa` 對齊 iMarine-FrontEnd `CwaWindow`：

```json
[
  {"window": "+3h", "rainLevel": "無", "beaufort": 6},
  {"window": "+6h", "rainLevel": "無", "beaufort": 6}
]
```

CWA API 失敗時，`extended_forecast_windows.available` 必須為 `false`，`cwa` 必須為空陣列，且不得影響 `forecast_anchors`。

## Live Verification

已用 `scripts/verify_cwa_extended_forecast_live.py` 實際呼叫 CWA API 驗證：

```text
data_id: F-D0047-065
location_name: 前鎮區
current_rain_probability: 0.1
next_rain_probability: 0.1
current_wind: wind_speed_text >= 11, beaufort_scale_min 6
next_wind: wind_speed_text >= 11, beaufort_scale_min 6
passed: true
```

報告：`kaohsiung_microclimate_lstm/results/dispatch_risk_v35/cwa_extended_forecast_live_verification.json`

## system-audit Response

`GET /api/v1/dispatch/system-audit?target_area=KHH` 必須保留：

```text
model_version
target_area
generated_at
system_status_summary
data_source_summary
station_summary
dataset_duration_summary
model_accuracy_summary
model_selection_summary
current_station_usage
dashboard_cards
dashboard_tables
trace
```

## Reports

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
kaohsiung_microclimate_lstm/results/model_benchmark_v13/wind_speed_gust_source_comparison/comparison_report.json
```

## Wind Speed/Gust Source Switch

`wind_speed_gust_prediction_source` controls only the base H1-H4 `wind_speed.predicted_mps` and `wind_gust.predicted_mps` source:

```text
legacy_lstm = default source, using the existing 467441 LSTM path.
nearby_cwa_historical_model = candidate source, using models/nearby_cwa_v32 wind_speed_H1-H4 and wind_gust_H1-H4 RandomForest artifacts.
```

When the candidate source is selected, inference features are built through `build_nearby_cwa_inference_feature_row()`, which reuses the nearby CWA historical training aggregation path. The response exposes `prediction_source` and `legacy_lstm_predicted_mps` on each wind speed/gust anchor so comparison is visible without changing the public risk schema.

The `port_local_postprocess` safety override remains downstream of the base prediction source. If KHWD realtime wind/gust exceeds operational thresholds, the postprocess override can still replace wind speed/gust operation level, operation label, and Beaufort fields.

Current formal comparison status:

```text
candidate_source: nearby_cwa_historical_model
baseline_source: legacy_lstm
available_khwd_rows: 42
min_required_khwd_rows: 500
formal_comparison_ready: false
recommended_default_source: legacy_lstm
```

## Wind Persistence Blending

Before `port_local_postprocess` safety overrides run, H1-H4 wind speed/gust display values are blended with KHWD realtime max observations when `port_local_wind_persistence_blending.enabled=true`.

```text
blended_mps = khwd_weight * khwd_live_max_mps + model_weight * base_model_predicted_mps
H1 weights: KHWD 0.8, model 0.2
H2 weights: KHWD 0.6, model 0.4
H3 weights: KHWD 0.4, model 0.6
H4 weights: KHWD 0.2, model 0.8
```

Each blended wind speed/gust object may expose:

```text
base_model_predicted_mps
predicted_mps
persistence_blending
prediction_source: <base_source>_khwd_persistence_blended
```

`predicted_mps`, `beaufort`, `operation_level`, and `operation_label` are recalculated from the blended value. The safety override remains downstream and can still raise levels when KHWD values cross hard thresholds.

## Data Source Roles

```text
KHWD = port-local realtime wind/gust source
nearby CWA historical = fallback historical model training reference
467441 = fallback baseline only
CWA PoP = rain prior only
CWA +3h/+6h = official forecast display only
```

## Current Validated State

```text
normal_prediction_mode: port_local_postprocess
no_realtime_khwd_mode_selected: nearby_cwa_historical_model
nearby_cwa_historical_model: trained / available / accepted
port_local_model: disabled / not trained
fallback_baseline: available_last_resort_only
```

## Registry And Runtime Reports

Nearby CWA wind/gust/rain inference resolves the accepted manifest through `models/model_registry.json` first, then falls back to the legacy `models/nearby_cwa_v32/model_manifest.json` path only when no accepted registry manifest is available.

`legacy_lstm` is now explicitly represented in the model registry and system-audit model accuracy summary because it remains the actual default base source for wind speed/gust until KHWD comparison data reaches the formal 500-row acceptance threshold.

Runtime JSON snapshots written by v29-v35 prediction calls use temp-file plus `os.replace` atomic writes. The same payloads are mirrored under `results/_live_cache/` to make their runtime-cache nature explicit; `_live_cache` is ignored by git.

Model-selection output now exposes `failed_reasons` and keeps the port-local model readiness failure visible in `selection_reason`, instead of only saying KHWD realtime data is available.
