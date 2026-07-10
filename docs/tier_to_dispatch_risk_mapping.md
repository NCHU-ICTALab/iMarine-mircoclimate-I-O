# Tier 架構與程式碼命名對照

本文件依 `高雄港微氣候預測_專案規格書_v1.3.md` 第 7 節第 7 項建立。後續文件、報告與 PR 描述應優先使用程式碼實際命名；Tier 僅保留為教學性分類。

| 教學性 Tier | 實際程式碼命名 | 主要模組/設定 | 用途限制 |
|---|---|---|---|
| Tier 1 骨幹模型 | `nearby_cwa_historical_model` | `src/training/train_nearby_cwa_historical_model.py`, `models/nearby_cwa_v32`, `models/nearby_cwa_v34` | KHWD 不可用時的 historical fallback，不是 port-local core。 |
| Tier 2 港區本地層 | `port_local_postprocess` | `src/postprocess`, `src/predict.py`, `config.yaml` | KHWD 即時安全門檻覆寫，H1-H4 均一套用，不做 horizon decay。 |
| Tier 2 港區本地 ML | `port_local_model` | `src/training/train_port_local_model.py`, `data/processed/port_local_training_dataset.parquet` | 仍待 KHWD/KHTD/KHAW 累積到訓練門檻，不應宣稱已正式啟用。 |
| Tier 3 fallback baseline | `fallback_baseline` / `467441` | `config.yaml`, `src/model_selection` | 僅 fallback，不進入 nearby CWA 訓練核心。 |
| Tier 4 外部 prior | `cwa_pop_prior` | `src/predict.py`, CWA forecast config | 只作降雨機率事後融合 prior，不作模型輸入特徵。 |
| 海象參考資料 | `cwa_marine_history` / `reference_only` | `src/data/fetch_marine_history.py`, `config/station_pool.yaml` | 不計入 `is_port_local`，目前只供 tide/surge readiness 與未來殘差模型。 |
| 雨量替代 QPE | `station_rainfall_qpe_fallback` | `src/data/fetch_qpesums.py`, `config.yaml` | `O-A0002-001` 自動雨量站 fallback，不是 QPESUMS 雷達格點。 |

## 寫作用語規則

- 對外描述模型選用時，使用 `port_local_postprocess`、`nearby_cwa_historical_model`、`fallback_baseline` 等程式碼命名。
- 可以在括號中補充 Tier 說明，例如 `nearby_cwa_historical_model`（教學分類 Tier 1）。
- 不應寫「Tier 1 目前直接作為港區本地核心」，因為 nearby CWA 站不可被計入 port-local core。
- 不應把 `O-A0002-001` 稱為 QPESUMS 雷達回波；它是自動雨量站 fallback。
- 不應把 `C4P01/1786/C4Q01/C4Q02/COMC08/46714D` 稱為 port-local station；它們是 `reference_only` marine/tide stations。
