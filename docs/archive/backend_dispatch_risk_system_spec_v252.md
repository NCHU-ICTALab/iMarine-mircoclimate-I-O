# 高雄港微氣候派工風險後端系統總規格書 v2.5.2

## 文件目的

本文件統整目前「高雄港微氣候派工風險預測系統」後端實作狀態，供後續維護、重構、前端串接與模型改善使用。現行系統的主要目標不是取代現場判斷，而是提供未來 30、60、90、120 分鐘的港區微氣候派工風險參考。

目前可直接提供派工參考的項目是風速、陣風與整合後的派工風險等級；降雨機率已可輸出，但模型成效仍偏弱，應以「提醒觀察」而非強制停工依據使用。

## 版本與入口

- 專案版本：`v2.5.2`
- 模型輸出版本：`kaohsiung_port_dispatch_risk_v2.5.2`
- 主要預測入口：`kaohsiung_microclimate_lstm.src.predict.predict_dispatch_risk_v252`
- API 入口：`GET /api/v1/dispatch/risk?target_station_id=467441`
- 目標測站：`467441`
- 時區：`Asia/Taipei`

API 會讀取 `kaohsiung_microclimate_lstm/data/raw/observed_hourly/{target_station_id}.csv`，並呼叫 `predict_dispatch_risk_v252()` 回傳 v2.5.2 JSON。若指定測站沒有本地觀測資料，API 回傳 404；若模型、config 或預測流程失敗，API 回傳 503。

## 預測錨點

系統固定輸出 4 個 forecast anchors：

| Anchor | 時距 | 用途 |
| --- | ---: | --- |
| H1 | +30 分鐘 | 最近期派工提醒 |
| H2 | +60 分鐘 | 短期作業安排 |
| H3 | +90 分鐘 | CWA PoP prior 可介入 |
| H4 | +120 分鐘 | CWA PoP prior 可介入 |

## 資料來源與使用方式

| 資料 | 現行角色 | 是否進入 LSTM input | 是否進入派工 max risk |
| --- | --- | --- | --- |
| 目標測站 `467441` 歷史觀測 | 雨量、風速、陣風模型主要輸入 | 是 | 間接，透過模型輸出 |
| 多測站附近雨量 | 降雨後處理參考 | 否 | 間接，透過 rain level |
| CWA OpenData PoP | H3/H4 降雨弱 prior | 否 | 間接，透過 rain level |
| 潮位 | 參考資訊 | 視模型資料而定 | 否 |
| 能見度 | optional，目前多為 unavailable | 否 | 否 |

CWA PoP 僅作為後處理 prior，不作為模型訓練或推論 input，避免 train-inference mismatch。若未來要把 CWA 預報納入模型 feature，必須先建立可回放的歷史 CWA forecast archive。

## CWA OpenData 與 Quality Gate

目前 resolved source：

- dataset：`F-D0047-091`
- location：前鎮區
- element：`3小時降雨機率`
- source resolution：`3h`
- resolved file：`kaohsiung_microclimate_lstm/config/resolved_cwa_forecast_source.json`

CWA PoP quality gate 會區分有效 `0%` 與缺值：

- raw `"0"` 或 `0` 且 parse ok：有效，可當作 0% 使用。
- `null`、missing、parse error、out of range、API error：無效，不套用 prior。

CWA prior 僅在以下條件同時成立時套用：

- anchor 為 `H3` 或 `H4`
- quality available
- parse status 為 `ok`
- normalized value 不為 `None`
- config 允許 `cwa_pop_prior.enabled`

## 風速與陣風

風速與陣風使用 regression 模型輸出 m/s，再轉為 Beaufort scale 與作業等級。現行成效如下：

| Target | H1 MAE | H2 MAE | H3 MAE | H4 MAE | 評估 |
| --- | ---: | ---: | ---: | ---: | --- |
| wind_speed | 0.534 | 0.537 | 0.588 | 0.578 | 可作派工參考 |
| wind_gust | 1.221 | 1.137 | 1.223 | 1.196 | 可作派工參考，但保守處理 |

陣風有 `gust_uncertainty_buffer_mps = 1.2` 的保守 buffer。派工風險等級使用 buffer 後的 operation level，輸出中仍保留 `original_level_without_buffer` 方便檢查。

## 降雨

降雨模型目前輸出 `rain_probability`，不是直接輸出未來雨量 mm 作派工判斷。現行降雨模型成效仍偏弱：

| Anchor | MAE | RMSE | CSI > 1mm | FAR > 1mm | 評估 |
| --- | ---: | ---: | ---: | ---: | --- |
| H1 | 1.632 mm | 5.189 mm | 0.110 | 0.835 | poor |
| H2 | 1.717 mm | 5.250 mm | 0.075 | 0.884 | poor |
| H3 | 1.409 mm | 5.067 mm | 0.148 | 0.733 | poor |
| H4 | 1.378 mm | 5.025 mm | 0.058 | 0.893 | poor |

因此降雨觸發 watch 時，現行 action 會因 reliability 為 `low_to_medium` 而降級為 `observe_only`，避免過度派工干預。

## 派工風險聚合

目前派工風險只納入：

- `rain_probability`
- `wind_speed`
- `wind_gust`

聚合規則：

```text
dispatch_risk_level = max(rain_level, wind_speed_level, wind_gust_level)
```

不納入：

- tide：reference only
- visibility：optional / unavailable
- marine transfer：low confidence

## Risk Trigger 語意

v2.5.2 的重要修正是 normal 狀態不得顯示任何風險觸發因子：

```json
{
  "primary_trigger": "none",
  "primary_trigger_level": "normal",
  "primary_trigger_reliability": null,
  "is_low_reliability_trigger": false
}
```

非 normal 狀態才依 priority 選主因：

```text
wind_gust > wind_speed > rain_probability > visibility > tide
```

## Dispatch Action

`dispatch_action_level` 由 `dispatch_risk_level` 與 `primary_trigger_reliability` 決定。低可靠度觸發因子會保守降級：

| dispatch risk | 高可靠度 action | 低可靠度 action |
| --- | --- | --- |
| normal | normal_dispatch | normal_dispatch |
| watch | monitor | observe_only |
| warning | restrict_sensitive_tasks | monitor |
| high_risk | delay_high_risk_tasks | restrict_sensitive_tasks |
| stop | suspend_exposed_tasks | delay_high_risk_tasks |

## API Contract

```http
GET /api/v1/dispatch/risk?target_station_id=467441
```

回傳格式為 v2.5.2 JSON，不額外包 v1 envelope。主要欄位：

- `model_version`
- `generated_at`
- `target_area`
- `forecast_anchors`
- `cwa_forecast`
- `data_availability`
- `reliability`
- `trace`

每個 anchor 主要欄位：

- `label`
- `offset_minutes`
- `timestamp`
- `rain.final_probability`
- `rain.level`
- `rain.source_detail.cwa_pop_quality`
- `wind_speed.predicted_mps`
- `wind_speed.beaufort`
- `wind_speed.operation_level`
- `wind_gust.predicted_mps`
- `wind_gust.beaufort`
- `wind_gust.operation_level`
- `dispatch_risk_level`
- `risk_trigger_detail`
- `dispatch_action_level`
- `dispatch_suggestion`

## 目前實跑輸出摘要

來源檔案：

- `kaohsiung_microclimate_lstm/results/dispatch_risk_v252/prediction_samples.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v252/metrics.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v252/cwa_fetch_report.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v252/reliability_report.json`

最新摘要：

| Anchor | dispatch risk | rain probability | primary trigger | action |
| --- | --- | ---: | --- | --- |
| H1 | watch | 0.3463 | rain_probability | observe_only |
| H2 | normal | 0.2960 | none | normal_dispatch |
| H3 | normal | 0.1474 | none | normal_dispatch |
| H4 | normal | 0.1899 | none | normal_dispatch |

風速與陣風預測：

| Anchor | wind speed m/s | wind gust m/s |
| --- | ---: | ---: |
| H1 | 1.352 | 4.149 |
| H2 | 1.218 | 3.433 |
| H3 | 1.063 | 3.346 |
| H4 | 1.537 | 3.361 |

目前解讀：H1 因降雨機率達 watch，但降雨模型可靠度仍低至中，因此只建議 `observe_only`；H2-H4 為 normal，且 `primary_trigger` 正確為 `none`。

## Trace 必須維持的語意

現行 v2.5.2 trace 必須保留：

```json
{
  "port_local_scope": true,
  "multi_station_input": true,
  "city_wide_forecast_as_target": false,
  "train_inference_mismatch_prevented": true,
  "cwa_pop_used_as_model_input": false,
  "cwa_pop_used_as_postprocess_prior": true,
  "cwa_pop_quality_gate_enabled": true,
  "zero_pop_distinguished_from_missing": true,
  "normal_state_primary_trigger_none": true,
  "risk_trigger_semantics_patch_applied": true,
  "dispatch_risk_aggregation": "max_level_rule"
}
```

## 測試

本次整合後需至少通過：

```powershell
python -m pytest tests/test_dispatch_risk_api.py tests/test_contracts.py tests/test_risk_trigger_semantics.py tests/test_risk_trigger_detail.py tests/test_action_mapping.py tests/test_predict_dispatch_risk_v252.py tests/test_predict_dispatch_risk_v251.py tests/test_cwa_pop_quality.py tests/test_cwa_anchor_alignment_quality.py tests/test_cwa_open_data_client.py tests/test_cwa_forecast_resolver.py tests/test_cwa_pop_prior.py tests/test_beaufort_scale.py tests/test_level_mapping.py tests/test_dispatch_risk_aggregator.py tests/test_rain_probability_rules.py tests/test_rain_probability_blender.py tests/test_lstm_baseline_preprocess.py
```

## 後續改善建議

1. 降雨模型應優先改善，方向包含 binary rain event classifier、LightGBM/XGBoost baseline、calibration、Brier Score、CSI、FAR、POD 追蹤。
2. 若要把 CWA PoP 作為模型 input，必須先建立歷史 CWA forecast archive，不能只拿即時 API 回填。
3. 多測站空間特徵可持續強化，但要避免把單一測站資料誤當成整個港區。
4. Tide 與 visibility 在資料品質足夠前維持 reference only / optional，不應直接進入 max risk。
