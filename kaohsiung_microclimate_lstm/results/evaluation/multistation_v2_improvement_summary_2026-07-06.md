# 高雄港微氣候多測站改善 v2 實作摘要

日期：2026-07-06

## 已實作項目

- 訓練參數更新：`max_epochs=150`、`patience=20`、`min_delta=0.0001`、`learning_rate=0.0005`、`ReduceLROnPlateau(patience=8, factor=0.5, min_lr=1e-5)`。
- 新增 loss CSV 與 loss plot 輸出：`logs/training/*_loss.csv`、`results/plots/*_loss.png`。
- 新增 CODiS 站台診斷工具：`src/data/diagnose_codis_stations.py`，輸出 `results/codis_diagnosis.csv`。
- 新增 467441 CODiS 10 分鐘資料抓取嘗試工具：`src/data/fetch_codis_10min.py`。
- 新增潮位諧和模型：`src/tide/harmonic_model.py`，已保存 `models/tide/*_harmonic_coef.pkl`。
- 新增 transfer fine-tune：`src/transfer/finetune.py`，由 467441 風速/陣風模型轉移至海象站。
- 新增 SpatialLSTM 架構支援與 config scaffolding，預設停用，保留後續多站空間模型擴充。

## 資料取得結果

- 已使用本專案既有 467441 hourly 資料重訓，資料期間約 180 天。
- CODiS 診斷共測試 432 組 stationType/dataType/date range 組合，全部回傳 0 筆。
- 467441 10 分鐘 CODiS 抓取工具已嘗試多組 `stationType` / `dataType`，目前 API 回傳 0 筆，因此本次仍採用 hourly 資料。

## 467441 模型成效

### 風速/陣風

- 模型：`baseline_lstm_v2`
- 測試視窗：270
- 權重：`models/checkpoints/467441_wind_speed_gust_best.pt`
- loss：`logs/training/467441_wind_speed_gust_loss.csv`
- loss 圖：`results/plots/467441_wind_speed_gust_loss.png`

| 變數 | H1 MAE/RMSE | H2 MAE/RMSE | H3 MAE/RMSE | H4 MAE/RMSE |
|---|---:|---:|---:|---:|
| wind_speed | 0.534 / 0.688 m/s | 0.537 / 0.690 m/s | 0.588 / 0.731 m/s | 0.578 / 0.721 m/s |
| wind_gust | 1.221 / 1.587 m/s | 1.137 / 1.507 m/s | 1.223 / 1.585 m/s | 1.196 / 1.574 m/s |

整體評估：風速四個時距皆為 excellent；陣風除 H1 為 acceptable 外，其餘為 excellent。陣風 H1/H2 尚未優於 persistence baseline。

### 雨量

- 模型：`baseline_lstm_v2`
- 測試視窗：270
- 權重：`models/checkpoints/467441_precipitation_best.pt`
- loss：`logs/training/467441_precipitation_loss.csv`
- loss 圖：`results/plots/467441_precipitation_loss.png`

| 變數 | H1 MAE/RMSE | H2 MAE/RMSE | H3 MAE/RMSE | H4 MAE/RMSE |
|---|---:|---:|---:|---:|
| precipitation_1hr | 1.443 / 5.791 mm | 1.443 / 5.791 mm | 1.365 / 5.711 mm | 1.365 / 5.711 mm |

整體評估：MAE 優於 persistence，但降雨事件偵測 CSI 為 0，等級仍為 poor。此結果代表模型偏向保守預測，對短延時強降雨事件仍不足。

## 潮位諧和模型成效

目前潮位來源 CSV 每站可用資料量很短，測試集僅 8 筆，因此此處結果只適合作為流程驗證，不適合作為正式成效宣稱。

| 測站 | MAE | RMSE | R2 | 備註 |
|---|---:|---:|---:|---|
| C4Q01 | 9.87 cm | 12.68 cm | 0.255 | 目前最佳 |
| C4Q02 | 78.51 cm | 95.77 cm | -37.339 | 資料不足且泛化差 |
| C4P01 | 62.61 cm | 75.30 cm | -72.406 | 資料不足且泛化差 |
| 1786 | 141.20 cm | 188.55 cm | -187.993 | 資料不足且泛化差 |

## Transfer Fine-tune

- C4Q01：已輸出 `models/checkpoints/C4Q01_wind_speed_gust_finetuned.pt`，30 epochs，最後 val_loss = 0.1848。
- C4Q02：已輸出 `models/checkpoints/C4Q02_wind_speed_gust_finetuned.pt`，30 epochs，最後 val_loss = 0.0249。
- COMC08：有效視窗為 0，輸出 `models/checkpoints/COMC08_wind_speed_gust_pretrain_only.json`，標記為 low confidence zero-shot transfer。

## 前端介面整合

可以整合到先前微氣候派工介面，但建議只接「微氣候預測」區塊，不納入派工規則。可提供的模型輸出如下：

- `station_id`
- `target_group`
- `forecast_generated_at`
- `anchor_offsets_minutes`: 30、60、90、120
- 風速/陣風：`wind_speed`、`wind_gust`，單位 m/s
- 雨量：`precipitation_1hr`，單位 mm
- 潮位：`tide_level`，單位 cm
- 品質欄位：`model_version`、`accuracy_grade`、`beats_persistence`、`data_window_status`

## 驗證

- `python -m pytest tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v2`
- 結果：2 passed
