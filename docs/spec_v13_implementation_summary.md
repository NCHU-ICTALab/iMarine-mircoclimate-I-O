# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-12 10:10（Asia/Taipei）

## 本輪完成

- 第 16 項已完成：缺值代碼污染已在 `historical_weather_normalizer.py` 源頭清理，並重建 nearby CWA processed parquet、訓練資料集與 `models/nearby_cwa_v32`。
- 雨量回歸採用 `log1p` 目標轉換；rain-event-only 訓練在正式評估中變差，未採用。
- 第 17 項已完成：`data/raw/observed_hourly/467441.csv` 的 159 筆負雨量缺值碼已依 `PHYSICAL_RANGE_LIMITS` 轉為空值。
- 第 18 項已完成修正：`extended_forecast_windows` 改用 CWA `F-D0047-065`，降雨機率取 `3小時降雨機率`，風速改以官方蒲福風級區間呈現，不再假裝有精確 m/s。
- v3.5 回應保留 frontend 相容 `cwa` 欄位，`beaufort` 使用官方蒲福風級下限。
- 第 19 項已完成：`rain.amount_level` 改回氣象雨量術語（無/小雨/大雨/豪雨/大豪雨），demo 頁面的降雨、風速、陣風分級不再顯示自創風險字眼。
- 第 20 項已完成：`port_local_postprocess` 安全門檻覆寫後，`operation_level`、`operation_label` 與扁平 `port_local_postprocess_applied` 已同步更新。
- 第 21 項已完成：安全門檻覆寫後 `beaufort` 改用 KHWD 即時觸發值換算；CWA PoP source 會依 `resolved_source_max_age_hours` 自動刷新；CWA dataset 解析度改用實際時間差優先判斷，並把 `F-D0047-065` 設為 3 小時候選第一順位。
- 第 22 項已完成候選接線：`wind_speed_gust_prediction_source` 新增 `legacy_lstm` / `nearby_cwa_historical_model` 開關，nearby CWA RF 風速/陣風模型已可用於 inference；因 KHWD 歷史列數不足正式比較門檻，預設仍維持 `legacy_lstm`。
- 第 23 項已完成：新增 `port_local_wind_persistence_blending`，H1~H4 風速/陣風會先依 KHWD 即時 max 與基礎模型預測做 persistence blending，再進入原本的 `port_local_postprocess` 安全門檻覆寫。
- 第 24~29 項已完成第一輪落地：nearby CWA 推論改由 registry accepted manifest 解析；registry 與 system audit 補 `legacy_lstm`；model selection reason 保留 port_local_model 未就緒原因；v29~v35 JSON 報告改原子寫入並同步 `_live_cache`；467441 清理補去重報告；新增低風險清理稽核報告；`load_config()` 加 mtime-aware cache。
- 第 30~33 項已完成：外顯 `model_version` 收斂為 `kaohsiung_port_dispatch_risk_v1.3`；`app/contracts.py` 的 `runtime_model_version` 改讀 `config.yaml`；所有 system spec API 的 `spec_version` 改為 `v1.3`；歷史 dispatch risk API contract 移到 `docs/archive/dispatch_risk_api_contract/`，現行文件改為 `docs/dispatch_risk_api_contract.md`；低風險清理稽核改為遞迴掃描 historical weather 站點。
- 第 34~36 項已完成：`docs/dispatch_risk_api_contract.md` 補上 Version History；`predict.py` 補上 v24~v35 wrapper chain 架構說明並新增 `predict_dispatch_risk_current()`；app API 與 CLI dispatch-risk 改用版本無關入口；依規格刪除 `test_predict_dispatch_risk_v24.py`、`v25.py`、`v251.py`、`v252.py` 四個早期 smoke 測試，保留 v29/v30/v32 與現行 v35/API 回歸測試。
- demo 頁面已新增「CWA +3h/+6h 官方預報」區塊，風速顯示蒲福風級文字，顏色由 `operation_level` 控制。

## 正式評估

資料清理與雨量訓練報告：
`kaohsiung_microclimate_lstm/results/model_benchmark_v13/data_cleaning_and_rain_training/comparison_report.json`

- Stage1：只做資料清理
  - wind_speed H1 R2：`0.3698 -> 0.7625`
  - wind_gust H1 R2：`0.8519 -> 0.8542`
  - precipitation_amount H1 R2：`-0.1054 -> 0.4510`
- Stage2：rain-event-only 雨量回歸，不採用
  - precipitation_amount H1 MAE：`0.3523 -> 5.8503`
  - precipitation_amount H1 R2：`0.4510 -> 0.2591`
- Stage3：在乾淨資料上加入 log1p，已採用
  - precipitation_amount H1 MAE：`0.3523 -> 0.2942`
  - precipitation_amount H1 R2：`0.4510 -> 0.4543`

## CWA Live Verification

已實際呼叫 CWA API 驗證 +3h/+6h 官方視窗：

- `data_id`: `F-D0047-065`
- `location_name`: `前鎮區`
- `current_rain_probability`: `0.1`
- `next_rain_probability`: `0.1`
- `current_wind`: `wind_speed_text >= 11`, `beaufort_scale_min 6`
- `next_wind`: `wind_speed_text >= 11`, `beaufort_scale_min 6`
- `passed`: `true`

報告：`kaohsiung_microclimate_lstm/results/dispatch_risk_v35/cwa_extended_forecast_live_verification.json`

已重新產生 CWA PoP resolved source：

- `dataset_id`: `F-D0047-065`
- `location_name`: `前鎮區`
- `element_name`: `3小時降雨機率`
- `source_resolution`: `3h`
- `valid_times`: `32`
- `resolved_at`: `2026-07-11T23:18:04+08:00`

真實 API 驗證：`GET /api/v1/dispatch/risk?target_area=KHH` 的 H3/H4 已套用 CWA prior，`cwa_prior_applied=true` 且 `cwa_source_resolution=3h`。

## 資料污染檢查

- `nearby_cwa_wind_speed_min` 負值筆數：0
- `nearby_cwa_precipitation_1hr_mean` 負值筆數：0
- `distance_weighted_precipitation` 負值筆數：0
- `target_nearby_precipitation_amount_H1` 負值筆數：0
- `467441.csv precipitation_1hr` 負值筆數：0

## 驗證

- 第 21 項目標回歸測試：`16 passed`
- 第 22 項目標回歸測試：`5 passed`
- 第 22 項評估報告：`results/model_benchmark_v13/wind_speed_gust_source_comparison/comparison_report.json`，`available_khwd_rows=42`、`min_required_khwd_rows=500`、`recommended_default_source=legacy_lstm`。
- 第 23 項目標回歸測試：`5 passed`；派工 API 相關回歸測試：`11 passed`。
- 第 24~29 項目標回歸測試：`34 passed`。
- 第 30~33 項目標回歸測試：`34 passed`。
- 第 34~36 項目標回歸測試：`19 passed`。
- 真實 API 驗證：`GET /api/v1/system/info` 與 `GET /api/v1/dispatch/system-audit?target_area=KHH` 皆回傳 `kaohsiung_port_dispatch_risk_v1.3`。
- 第 32 項實際清理報告：`low_risk_cleanup_report.json` 現在會列出 `C0V610`、`C0V680` 為未被訓練選用的 extra historical weather stations。
- 第 28 項實際清理報告：`observed_hourly_467441_cleaning_report.json` 已揭露 `duplicate_rows_detected=8`、`duplicate_rows_removed=4`、`latest_obs_time=2026-07-05T23:00:00+08:00`。
- 第 29 項低風險清理報告：`results/dispatch_risk_v35/low_risk_cleanup_report.json`，採 report-only，不刪資料。
- 真實 API 驗證：`GET /api/v1/dispatch/risk?target_area=KHH` 回傳 H1/H2 wind_speed `stop` 與 wind_gust `high_risk` 時，label 與 flat applied 欄位皆一致。
- 真實候選切換驗證：臨時設定 `wind_speed_gust_prediction_source=nearby_cwa_historical_model` 時，v35 回應 `effective_source=nearby_cwa_historical_model`，H1/H2 使用 nearby CWA RF 輸出。
- 真實 persistence blending 驗證：目前 KHWD max wind/gust 為 `10.152/11.33 m/s`，H1 風速由模型原始 `1.352` 混合為 `8.392 m/s`，H2~H4 依 0.6/0.4/0.2 權重遞減。
- 真實 selection reason 驗證：v35 `selection_reason` 已明確列出 port_local_model 未就緒原因，包括 `sample_count below min_total_samples` 與 H1~H4 label 不足。
- 完整測試：`238 passed, 4 warnings`（warnings 皆為既有 FastAPI `@app.on_event` deprecation warning）。
- 目前僅剩 FastAPI `@app.on_event` deprecation warning，非本輪功能錯誤。

## 仍需時間累積的項目

- CWA 歷史預報持續記錄機制目前只能等待 14 天以上快照累積。
- `port_local_model` 的 KHWD ML 訓練仍需等待港區本地資料自然累積到訓練門檻。

## 2026-07-12 第37項更新

- 已新增 `kaohsiung_microclimate_lstm/src/io_utils.py::atomic_write_json()`，統一處理 JSON report 原子寫入。
- `predict.py` 與 `system_audit.py` 已改用共用 helper，移除固定 `.{path.name}.tmp` 暫存檔競爭問題。
- 寫入策略改為 `tempfile.mkstemp()` 唯一暫存檔、同程序同目標路徑 replace lock、`os.replace()` 失敗時 3 次短暫重試，避免 Windows 並發請求導致 `WinError 32` / `PermissionError` 讓 API 500。
- 新增 `tests/test_atomic_json_write.py`，涵蓋多執行緒同一路徑並發寫入與 transient replace failure retry。
- 完整測試：`python -m pytest` -> `240 passed, 4 warnings`；warnings 仍為既有 FastAPI `@app.on_event` deprecation warning。

## 2026-07-12 第38~39項更新

- 第39項已完成：`predict.py` 新增 manifest artifact path 解析 helper，優先讀取 v34 巢狀 `models[base_key].artifacts[base_key_Hn].artifact_path`，並保留 v32 扁平 `model_path` / 字串格式相容。
- `_predict_nearby_precipitation_amounts()` 與 `_predict_nearby_wind_variable()` 已共用同一解析邏輯，修正高降雨機率時 `rain.predicted_amount_mm` / `amount_level` 可能為 `null` 的問題，也修正 `nearby_cwa_historical_model` 風速/陣風候選路徑讀不到 v34 manifest 的問題。
- 第38項已完成：`app/api.py` 改用 FastAPI lifespan context manager，移除 `@app.on_event` deprecation warning，保留 scheduler startup/shutdown 行為。
- 新增/更新測試：巢狀 v34 manifest 降雨量、風速/陣風解析，以及 v35 高降雨機率端對端非空降雨量回歸測試。
- 完整測試：`python -m pytest` -> `243 passed`，目前無 warning。

## 2026-07-12 第40~43項更新

- 第40項已完成：`atomic_write_json()` 增加相同內容跳過寫入、20 次 replace retry 與較長退避；`model_registry.py` 的 v34 manifest / registry 寫入改用 atomic write；API 層新增 10 秒 TTL dispatch risk cache 與 singleflight，避免高並發重複跑完整預測與大量 report I/O。
- 第41項已完成：`validate_model_manifest()` 會遞迴檢查 v34 巢狀 `artifacts` 的 H1~H4 `artifact_path/model_path`，補上 H2 缺檔回歸測試。
- 第42項已完成：`system_audit.py::_build_model_accuracy_summary()` 改用 `validate_model_manifest()`，模型 `available` 會反映實體 artifact 是否存在，補上缺檔時不可用的回歸測試。
- 第43項已完成：`microclimate_observations` 新增 `idx_obs_lookup(device_type, station_id, is_forecast, obs_time)`，`latest_by_device_type()` 改為 CTE + indexed join。
- 實測：`ObservationStore.latest_by_device_type()` 對 `microclimate.sqlite3` 回傳 29 筆耗時約 `0.0066` 秒，查詢計畫使用 `idx_obs_lookup`。
- 實測：50 並發混打 `/api/v1/dispatch/risk`、`/api/v1/dispatch/station-usage`、`/api/v1/dispatch/model-status` 三輪皆 `50/50` 回 200，無 WinError/503；冷快取最慢約 `8.8s`，熱快取輪次約 `0.4s` 內完成。
- 完整測試：`python -m pytest` -> `247 passed`。

## 2026-07-12 第44項更新

- 第44項已完成：降雨機率 CWA prior 改成 H1~H4 全套用，權重比照風速持續性混合的使用者指定數字。
- `config.yaml::cwa_pop` 與 `cwa_pop_prior` 已新增權重表：H1 `own=0.8/cwa=0.2`、H2 `0.6/0.4`、H3 `0.4/0.6`、H4 `0.2/0.8`。
- 正式 config 已移除舊的全域 `max_adjustment_weight/max_weight` 與 `resolution_weight_cap`；`apply_cwa_pop_prior()` 直接依每個 anchor 的權重表融合，不再疊加解析度上限。
- `apply_cwa_pop_prior()` 的 trace/source_detail 會輸出各 anchor 的 `own_weight`、`cwa_weight`；新增測試確認 H1/H2 也會 `cwa_prior_applied=true`。
- 完整測試：`py -3.13 -m pytest` -> `247 passed`。

## 2026-07-12 第45~47項更新

- 第45項已完成：`pop3h_client._current_next()` 的降雨機率改用 target-time 查找，`current` 對應 `now+3h`，`next` 對應 `now+6h`；保留既有鍵名避免破壞呼叫端。
- 第46項已完成：CWA prior 新增 `weight_profile` / `profiles`。預設 `conservative` 回到 H1/H2 不套 CWA、H3/H4 `cwa_weight=0.2`；第44項的 `0.2/0.4/0.6/0.8` 保留為 `graduated_like_wind` 候選 profile。
- 第47項已完成：`fetch_pop3h(force_refresh=True)` 會跳過有效快取；`run_microclimate_source_fetch()` 新增 `cwa_extended_forecast` 任務，手動「抓取最新資料」會強制刷新 +3h/+6h 卡片快取。
- 實際 API 驗證：預設 `/api/v1/dispatch/risk?target_area=KHH` 回傳 H1/H2 `cwa_prior_applied=false`，H3/H4 `cwa_weight=0.2`；extended forecast 卡片目前 +3h=`0.5`、+6h=`0.2`，不再同值。
- 完整測試：`py -3.13 -m pytest` -> `251 passed`。
