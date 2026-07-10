# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-10 21:16（Asia/Taipei）

## 本次依更新後規格書完成

- 雨量 mm 即時來源已改接 `nearby_cwa_live` 六站。
  - `predict_dispatch_risk_v27()` 會從 `station_pool.yaml` 動態找出 `role: nearby_cwa_live_reference` 的 CWA 站。
  - CWA 即時站資料專門提供給雨量機率與雨量 mm 計算。
  - KHWD 仍只用於港區風速/陣風 safety floor，不與雨量資料混用。
  - smoke 結果：`amount_source=nearby_cwa_live_observations`。

- 雨量 mm 回歸已改為條件式輸出。
  - 若該 horizon 的降雨機率低於門檻，`predicted_amount_mm` 直接回 0。
  - 若降雨機率達門檻，才使用 `precipitation_amount_H1~H4` 回歸模型。

- 新增 H1-H3 三小時累積雨量估計。
  - `three_hour_accumulation_estimate.predicted_amount_mm` 為 H1、H2、H3 的 `predicted_amount_mm` 加總。
  - 輸出明確標註：這是 H1-H3 預測值加總，不是真正 3 小時觀測累積。

- 新增潮汐增水殘差訓練腳本。
  - 檔案：`kaohsiung_microclimate_lstm/src/tools/train_surge_residual_model.py`
  - 方法：先用 harmonic model 估天文潮，再以 `實測潮位 - 天文潮` 作為 surge residual label。
  - 已用 C4P01 作為主要潮位站，C4Q01/C4Q02/COMC08/46714D 作為氣壓、風、波浪特徵來源完成訓練。

## 訓練結果

- nearby CWA backbone 重新訓練完成。
  - 六站：C0V890、C0V490、C0V840、C0V810、C0V450、C0V900
  - sample_count: 184,614
  - training_days: 1,282
  - readiness: true
  - registry validation: true

- 雨量 mm H1 指標：
  - MAE: 0.6018 mm
  - RMSE: 13.6970 mm
  - R2: -0.1054
  - bias: 0.0967
  - beats_persistence: true

- surge residual C4P01 訓練結果：
  - rows: 727
  - train_rows: 581
  - test_rows: 146
  - surge_residual_MAE: 0.0610
  - surge_residual_RMSE: 0.0753
  - surge_residual_R2: -0.1823
  - tide_level_MAE: 0.0610
  - tide_level_RMSE: 0.0753
  - tide_level_R2: 0.7905

## Smoke

- `prediction_mode=port_local_postprocess`
- `anchor_time_source=port_local_khwd`
- H1 timestamp: `2026-07-10T21:00:00+08:00`
- H1 rain probability: `0.7`
- H1 `predicted_amount_mm=4.849`
- H1 `amount_level=watch`
- H1 `amount_source=nearby_cwa_live_observations`
- H1-H3 3hr estimate: `9.698 mm`, level `watch`

## 驗證

- 全測試：`220 passed`

## 仍需注意

- CWA vs 本模型公平比較仍需累積 F-D0047 系列歷史預報快照至少 14 天。
- 雨量 mm 模型已可用即時 CWA 站，但目前 CWA live 站本地即時檔仍只有少量筆數；lag/rolling 特徵會隨排程累積後更有意義。
- surge residual 模型已可訓練，但 residual R2 仍偏弱；目前可作為初版 artifact，後續應持續累積資料並評估更多特徵。
