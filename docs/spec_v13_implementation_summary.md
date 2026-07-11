# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-11 21:26（Asia/Taipei）

## 本輪完成

- 第 16 項已完成：缺值代碼污染已在 `historical_weather_normalizer.py` 源頭清理，並重建 nearby CWA processed parquet、訓練資料集與 `models/nearby_cwa_v32`。
- 雨量回歸採用 `log1p` 目標轉換；rain-event-only 訓練在正式評估中變差，未採用。
- 第 17 項已完成：`data/raw/observed_hourly/467441.csv` 的 159 筆負雨量缺值碼已依 `PHYSICAL_RANGE_LIMITS` 轉為空值。
- 第 18 項已完成修正：`extended_forecast_windows` 改用 CWA `F-D0047-065`，降雨機率取 `3小時降雨機率`，風速改以官方蒲福風級區間呈現，不再假裝有精確 m/s。
- v3.5 回應保留 frontend 相容 `cwa` 欄位，`beaufort` 使用官方蒲福風級下限。
- demo 頁面已新增「CWA +3h/+6h 官方預報」區塊。

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

## 資料污染檢查

- `nearby_cwa_wind_speed_min` 負值筆數：0
- `nearby_cwa_precipitation_1hr_mean` 負值筆數：0
- `distance_weighted_precipitation` 負值筆數：0
- `target_nearby_precipitation_amount_H1` 負值筆數：0
- `467441.csv precipitation_1hr` 負值筆數：0

## 驗證

- 完整測試：`219 passed`
- 目前僅剩 FastAPI `@app.on_event` deprecation warning，非本輪功能錯誤。

## 仍需時間累積的項目

- CWA 歷史預報持續記錄機制目前只能等待 14 天以上快照累積。
- `port_local_model` 的 KHWD ML 訓練仍需等待港區本地資料自然累積到訓練門檻。
