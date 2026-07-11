# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-11 12:30（Asia/Taipei）

## 本次新增

- 已完成規格書第 13 章：把 `config/zoning.yaml` 的上下游站點配對接入 nearby CWA 歷史資料特徵工程，**但評估後決策為預設關閉、不進正式模型**（見下方「複核與修正」）。
- `config/zoning.yaml` 已新增 `season_month_ranges` 與 `typhoon_season_months`；颱風季月份優先回傳 `typhoon`，不套用固定上下游配對。
- 新增 `kaohsiung_microclimate_lstm/src/data/upstream_lead_features.py`：
  - `resolve_season()`：依月份規則判斷季節。
  - `build_upstream_lead_features()`：依當下季節取 `upstream_station_ids ∩ selected_station_ids`，產生 `upstream_subset_*` mean/max 特徵。
  - 上游交集為空時回傳 `NaN`，不以 0 補值。
- `nearby_historical_training_dataset.py` 已在 `_aggregate(raw)` 後合併 upstream 特徵（**僅在 `nearby_cwa_historical_training.enable_upstream_lead_features: true` 時才合併，預設 false**），並對 wind/gust/rain 的 upstream max 欄位產生 lag1/roll3，雨量另產生 roll3/roll6。
- 雨量 mm 回歸特徵集已允許 upstream 降雨欄位，但仍排除同時刻 wind_speed/wind_gust，維持無洩漏特徵政策。
- 新增 `evaluate_upstream_lead_features.py`，可輸出 baseline vs. with-upstream 的比較報告。

## 複核與修正（2026-07-11 12:30，重要）

codex 原始評估工具（`evaluate_upstream_lead_features.py`）預設用**最近 20,000 筆資料、fast RandomForest 30 estimators** 做比較，並在此基礎上得出「wind_speed/wind_gust 小幅改善」的結論，且把 upstream 特徵**無條件**合併進正式訓練資料集（無開關）。

複核時發現這個簡化版評估的 baseline 數字與真正生產模型的已知指標差異極大（例如 wind_speed H1 R² 在簡化版 baseline 是 -0.27，但正式模型實測是 +0.37），因此**用正式規模重跑**（全部 30,769 筆聚合資料、`n_estimators=80`，與 `config.yaml` 生產設定完全一致）：

| 目標 | 不含上游特徵 | 含上游特徵 | 結論 |
| --- | --- | --- | --- |
| wind_speed H1 | R²=0.3698 | R²=0.3658 | 變差 |
| wind_speed H3 | R²=0.3329 | R²=0.3304 | 變差 |
| wind_gust H1 | R²=0.8519 | R²=0.8525 | 幾乎持平 |
| precipitation_amount H1 | R²=-0.1054 | R²=-0.1049 | 幾乎持平 |

正式規模下並未觀察到規格書 §13.3 要求的「確實優於 baseline」，wind_speed 甚至略變差。**已修正**：

- `config.yaml` 新增 `nearby_cwa_historical_training.enable_upstream_lead_features: false`（預設關閉）。
- `nearby_historical_training_dataset.py` 改為僅在此旗標為 true 才合併 upstream 特徵。
- 已重建 `nearby_cwa_training_dataset_v32.parquet` 回復為不含 upstream 欄位版本（30,769 筆聚合資料，與線上模型的特徵集一致）。
- 新增回歸測試 `test_nearby_historical_training_dataset_upstream_lead_features_disabled_by_default`，驗證預設關閉時不會合併上游欄位。

這是本規格書第二次出現「簡化版 benchmark 結論在正式規模下不成立」（第一次是第 7 節第 2b 項 wind_speed 換 LightGBM 又撤回），教訓一致：任何模型比較決策前必須用正式訓練規模重跑驗證。

## 既有 v1.3 成果

- 已完成手動抓取端點 `POST /admin/fetch-microclimate-sources` 與 demo 頁面「抓取最新資料」按鈕。
- 已完成預設關閉的自動排程基礎建設與 `GET /admin/scheduler-status`。
- 降雨量 mm 來源已改接 `nearby_cwa_live` 六站，不再誤用 KHWD 港區風速資料。
- 派工輸出已新增 H1-H3 三小時累積估計，並明確標註這是 H1~H3 預測值加總。
- 已新增並訓練增水殘差模型腳本。

## 驗證

- 完整測試：`204 passed`
- 已新增/覆蓋測試：
  - 季節月份判斷與颱風季優先。
  - 上游站交集為空時回傳 NaN。
  - nearby CWA 訓練資料集接入 upstream lead features（明確啟用旗標時）。
  - **預設關閉時不會合併上游欄位（新增回歸測試）**。
  - upstream 評估工具可輸出比較報告。
  - 既有手動抓取與排程端點仍通過。

## 注意事項

- FastAPI `@app.on_event` 目前可正常運作，但測試仍會出現 deprecation warning；後續可改成 lifespan 寫法。
