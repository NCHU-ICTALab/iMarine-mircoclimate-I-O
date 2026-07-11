# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-11 13:08（Asia/Taipei）

## 本次新增

- 已完成規格書第 14 章／第 7 節第 15 項：氣壓、濕度、氣溫、露點差與測站間氣壓梯度特徵接入評估。
- `nearby_historical_training_dataset.py` 已新增候選特徵：
  - `nearby_cwa_pressure_*`
  - `nearby_cwa_relative_humidity_*`
  - `nearby_cwa_temperature_*`
  - `nearby_cwa_dew_point_mean`
  - `nearby_cwa_dew_point_spread_mean`
  - `nearby_cwa_pressure_gradient`
  - `nearby_cwa_pressure_mean_trend_3h`
- 新增 `nearby_cwa_historical_training.enable_pressure_humidity_features`，目前預設 `false`。
- 新增 `evaluate_pressure_humidity_features.py`，會用完整資料與正式訓練設定比較 baseline 與氣壓/濕度特徵版。

## 正式評估

- 報告：`kaohsiung_microclimate_lstm/results/model_benchmark_v13/pressure_humidity_features/comparison_report.json`
- `evaluation_mode`: `full_scale_production_config`
- 聚合後訓練樣本：30,769 筆
- 未抽樣、未降低模型樹數。

評估結論：
- wind_speed：H1-H4 變差，MAE 增加 `+0.0063` 到 `+0.0161`，R2 下降 `-0.0081` 到 `-0.0491`。
- wind_gust：H1-H4 小幅改善，MAE 下降 `-0.0040` 到 `-0.0091`。
- rain_probability：AUC 小幅改善 `+0.0019` 到 `+0.0183`，但 CSI 下降 `-0.0097` 到 `-0.0131`。
- precipitation_amount：R2 改善，但 MAE 變差 `+0.0097` 到 `+0.1199`。

結論：結果不是穩定全面改善，因此依規格 §14.3，保留為候選特徵但不預設啟用。

## 既有 v1.3 成果

- 手動抓取端點與 demo「抓取最新資料」按鈕已完成。
- 預設關閉的自動排程基礎建設已完成。
- 上下游領先特徵已接入但正式評估後預設關閉。
- 降雨量 mm 來源已改接 nearby CWA 六站。
- H1-H3 三小時累積估計與增水殘差模型已完成。

## 驗證

- 完整測試：`209 passed`
- 已新增/覆蓋測試：
  - `_dew_point_c()` 露點公式邊界。
  - `enable_pressure_humidity_features` 預設關閉時不產生新欄位。
  - 開啟後產生氣壓、濕度、氣溫、露點差、氣壓梯度與 3 小時氣壓趨勢。
  - 氣壓/濕度正式評估工具的設定切換與比較邏輯。

## 注意事項

- FastAPI `@app.on_event` 仍有 deprecation warning，不影響功能。
