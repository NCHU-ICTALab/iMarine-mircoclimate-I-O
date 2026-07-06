# 2026-07-06 實際訓練摘要

## 資料來源

- CWA marine rolling 48h：288 筆，已寫入 `microclimate.sqlite3`。
- CODiS 高雄站 `467441`：180 天逐時資料 4140 筆，已寫入 `microclimate.sqlite3`。
- 匯出訓練 CSV：`kaohsiung_microclimate_lstm/data/raw/observed_hourly/`。

## 保存輸出

- 權重 checkpoint：`kaohsiung_microclimate_lstm/models/checkpoints/*.pt`
- scaler：`kaohsiung_microclimate_lstm/scalers/*.pkl`
- 評估報告：`kaohsiung_microclimate_lstm/results/evaluation/*_metrics.json`
- 摘要 CSV：`kaohsiung_microclimate_lstm/results/evaluation/summary_report.csv`
- 訓練 log：`kaohsiung_microclimate_lstm/logs/training/*.json`

## 主要成效

### 高雄站 467441，180 天逐時資料

`wind_speed_gust`：

- 測試窗口：270
- best val loss：0.023554
- 整體是否打敗 persistence：否
- `wind_speed` MAE：H1 0.756、H2 0.831、H3 0.860、H4 0.707 m/s
- `wind_gust` MAE：H1 1.990、H2 1.706、H3 1.464、H4 1.729 m/s

`precipitation`：

- 測試窗口：270
- best val loss：0.273098
- 整體是否打敗 persistence：是
- MAE：H1 1.443、H2 1.443、H3 1.365、H4 1.365 mm
- 但 H1-H4 皆為 `poor`，代表降雨事件辨識仍不足。

### Marine rolling 48h，短樣本訓練

潮位模型：

- `C4P01` MAE：H1 13.094、H2 18.992、H3 24.185、H4 18.170 cm
- `C4Q01` MAE：H1 16.763、H2 9.369、H3 19.555、H4 16.215 cm
- `C4Q02` MAE：H1 23.980、H2 12.319、H3 15.282、H4 16.375 cm
- `1786` MAE：H1 14.056、H2 21.060、H3 22.568、H4 16.066 cm
- 整體皆未打敗 persistence。這批資料只有 48 小時，不適合作為正式潮位模型成效判斷。

Marine 風速/陣風模型：

- `C4Q01` 未打敗 persistence，H1 風速與陣風為 `poor`。
- `C4Q02` H2/H3 風速與 H2 陣風有打敗 persistence，但整體仍未打敗。
- 因測試窗口只有 6，僅能作為流程驗證。

## 結論

目前已完成並保存實際可推論的 LSTM checkpoint，但模型成效分兩類：

- `467441 precipitation` 在 180 天資料上有打敗 persistence，但準確度分級仍差。
- `467441 wind_speed_gust` 指標落在規格門檻內，但未打敗 persistence，代表短期風速用 persistence 仍更強。
- Marine 潮位/風速只有 rolling 48h，訓練樣本太少，不能作為正式模型。

正式導入前，建議至少累積 3-6 個月港區潮位、風速、陣風與降雨資料，再重訓。
