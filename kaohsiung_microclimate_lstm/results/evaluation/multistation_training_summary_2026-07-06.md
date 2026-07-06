# 2026-07-06 多測站訓練摘要

## 資料抓取策略

原則：能抓 180 天就使用 180 天；抓不到長期歷史時，才退回較短 rolling 資料。

### CODiS 180 天

已測試高雄港區與近港 CWA 測站：

- C0V840 鳳鼻頭
- C0V890 前鎮
- C0V810 左營
- C0V450 鳳森
- C0V700 三民
- C0V690 鼓山
- C0V710 苓雅
- 467441 高雄
- 468100 東沙島
- 469020 南沙島
- CAP070 高雄燈塔

結果：只有 `467441 高雄` 能從 CODiS fallback 抓到 180 天逐時資料。其他站在 CODiS `cwb/auto` 類型測試皆回傳 0 筆。

`467441` 最終資料：

- 筆數：4144
- 時間：2026-01-07 01:00 到 2026-07-05 23:00
- 欄位：wind_speed、wind_gust、wind_direction、precipitation_1hr、visibility

### Marine rolling 48h

可用短資料：

- C4P01 高雄潮位站：48 筆 tide_level
- 1786 永安潮位站：48 筆 tide_level
- C4Q01 小琉球潮位站：48 筆 wind/tide
- C4Q02 東港潮位站：48 筆 wind/tide
- COMC08 彌陀資料浮標：48 筆，其中 wind 有效約 36 筆
- 46714D 小琉球資料浮標：wind 有效約 6 筆

COMC08 與 46714D 因 12h lookback + 2h horizon 找不到足夠完整有效窗口，未訓練。

## 模型輸出

每個模型的 `predict()` 回傳：

- `station_id`
- `target_group`
- `anchors`
  - H1：+30 min
  - H2：+60 min
  - H3：+90 min
  - H4：+120 min
  - 每個 anchor 含 timestamp 與目標變數預測值
- `accuracy_grade`
- `model_version`
- `generated_at`

目標群組：

- `wind_speed_gust`：輸出 `wind_speed`、`wind_gust`，單位 m/s
- `precipitation`：輸出 `precipitation_1hr`，單位 mm
- `tide_level`：輸出 `tide_level`，單位 cm

實際輸出樣本：`prediction_samples_2026-07-06.json`

## 表現摘要

### 467441 高雄，180 天逐時資料

`wind_speed_gust`

- 測試窗口：270
- epochs：10
- best val loss：0.023554
- 是否整體打敗 persistence：否
- wind_speed MAE：H1 0.756、H2 0.831、H3 0.860、H4 0.707 m/s
- wind_gust MAE：H1 1.990、H2 1.706、H3 1.464、H4 1.729 m/s
- 解讀：風速/陣風誤差落在可接受範圍，但 persistence 在短期仍更強，表示模型尚未學到足夠優勢。

`precipitation`

- 測試窗口：270
- epochs：10
- best val loss：0.273098
- 是否整體打敗 persistence：是
- MAE：H1 1.443、H2 1.443、H3 1.365、H4 1.365 mm
- accuracy_grade：H1-H4 皆為 poor
- 解讀：平均誤差有改善，但降雨事件判別仍不佳。

### Marine 48h 短資料

`C4P01 tide_level`

- 測試窗口：6
- MAE：H1 13.094、H2 18.992、H3 24.185、H4 18.170 cm
- 是否整體打敗 persistence：否

`1786 tide_level`

- 測試窗口：6
- MAE：H1 14.056、H2 21.060、H3 22.568、H4 16.066 cm
- 是否整體打敗 persistence：否

`C4Q01 tide_level`

- 測試窗口：6
- MAE：H1 16.763、H2 9.369、H3 19.555、H4 16.215 cm
- 是否整體打敗 persistence：否

`C4Q02 tide_level`

- 測試窗口：6
- MAE：H1 23.980、H2 12.319、H3 15.282、H4 16.375 cm
- 是否整體打敗 persistence：否

`C4Q01 wind_speed_gust`

- 測試窗口：6
- wind_speed MAE：H1 1.542、H2 1.630、H3 1.658、H4 1.813 m/s
- wind_gust MAE：H1 2.448、H2 2.368、H3 1.819、H4 2.008 m/s
- 是否整體打敗 persistence：否

`C4Q02 wind_speed_gust`

- 測試窗口：6
- wind_speed MAE：H1 1.305、H2 0.507、H3 0.477、H4 2.548 m/s
- wind_gust MAE：H1 1.282、H2 0.812、H3 2.720、H4 1.753 m/s
- 是否整體打敗 persistence：否

## 結論

- 已完成多測站嘗試與訓練保存。
- 真正可用 180 天資料的目前只有 `467441`。
- Marine 多測站目前只能用 48 小時 rolling 資料，樣本太少，不建議作為正式模型成效。
- 若要正式多測站部署，需要建立長期港區資料儲存排程，至少累積數月 TWPort 與 marine 歷史。
