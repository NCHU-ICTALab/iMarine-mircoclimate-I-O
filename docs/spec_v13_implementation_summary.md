# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-11 18:55（Asia/Taipei）

## 本輪完成

- 第 16 項「缺值代碼污染清除與雨量回歸訓練方法優化」已完成。
- `historical_weather_normalizer.py` 已在資料源頭加入物理範圍檢查，將 `-99.x` 風速缺值碼、`-999.6` 雨量缺值碼與其他超出合理範圍的值轉成 `NaN`。
- 已重建 `data/processed/nearby_cwa_historical/*.parquet`。
- 已重建 `data/processed/nearby_cwa_training_dataset_v32.parquet`。
- 已重訓正式模型 `models/nearby_cwa_v32`。
- 雨量回歸採用 `log1p` 目標轉換：`precipitation_amount_training.log1p_target: true`。
- rain-event-only 雨量訓練在正式評估中變差，未採用：`train_on_rain_events_only: false`。
- 預測端已支援 `target_transform=log1p` 時用 `expm1()` 還原雨量輸出，避免線上輸出停留在 log 尺度。
- KHWD08 metadata 語意已對齊規格書：已確認非公開、不再追蹤；KHWD08 僅作即時校核，不用於需要座標的空間特徵。

## 正式評估

報告位置：`kaohsiung_microclimate_lstm/results/model_benchmark_v13/data_cleaning_and_rain_training/comparison_report.json`

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
  - precipitation_amount H3 MAE：`0.4498 -> 0.3521`
  - precipitation_amount H3 R2：`0.2543 -> 0.2632`

## 資料污染檢查

- `nearby_cwa_wind_speed_min` 負值筆數：0
- `nearby_cwa_precipitation_1hr_mean` 負值筆數：0
- `distance_weighted_precipitation` 負值筆數：0
- `target_nearby_precipitation_amount_H1` 負值筆數：0

## 已對齊的既有項目

- 派工示範頁面已改為繁體中文。
- 手動抓取最新資料按鈕已完成。
- 自動排程基礎建設已完成，預設關閉。
- 上下游領先特徵、氣壓/濕度/氣溫特徵皆已完成正式評估，結論是不預設啟用。
- H1-H3 三小時累積雨量估計與潮汐增水殘差模型已完成初版。

## 驗證

- 完整測試：`214 passed`
- 目前僅剩 FastAPI `@app.on_event` deprecation warning，非本輪功能錯誤。

## 仍需時間累積的項目

- CWA 歷史預報持續記錄機制目前只能等待 14 天以上快照累積，屬時間問題。
- `port_local_model` 的 KHWD ML 訓練仍需等待港區本地資料自然累積到訓練門檻。
