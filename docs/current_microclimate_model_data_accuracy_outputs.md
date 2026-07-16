# 高雄港微氣候模型現況：資料、準確度與輸出

更新日期：2026-07-16  
模型版本：`kaohsiung_port_dispatch_risk_v1.3`  
主要 API：`GET /api/v1/dispatch/risk?target_area=KHH`  
主要預測入口：`kaohsiung_microclimate_lstm.src.predict.predict_dispatch_risk_current`

## 1. 目前結論

目前正式派工風險輸出不是單一 LSTM 模型。系統以「可用資料優先」的階層式流程產生 H1~H4 預測：

| 優先順序 | 資料/模型 | 目前用途 | 狀態 |
|---|---|---|---|
| Tier 1 | Nearby CWA/CODiS 六站歷史模型 | 目前主要骨幹，負責風速、陣風、降雨機率、雨量推估 | 可用 |
| Tier 2 | KHWD 港區即時資料 | 作為港區即時後處理與模式選擇參考 | 可用但歷史累積仍不足以訓練 KHWD-only 模型 |
| Tier 3 | 467441 高雄測站 | fallback 與歷史相容資料源 | 可用 |
| 官方預報融合 | CWA `F-D0047-065` | 降雨機率 prior、+3h/+6h 官方卡片、風速/陣風/能見度官方欄位 | 可用 |
| 海象資料 | 商港海象 `O-B0075-001` | 即時/短期展示與未來潮汐增水模型資料來源 | 目前歷史累積不足，未訓練 |

`port_local_model` 目前先不訓練，原因是 KHWD 與海象資料仍缺乏足夠、連續、可回測的歷史樣本。正式輸出仍以 nearby CWA historical model 搭配 KHWD 即時後處理為主。

## 2. 主要資料來源

| 類別 | 檔案/來源 | 實際用途 | 備註 |
|---|---|---|---|
| Nearby CWA/CODiS | `data/raw/observed_hourly/C0V*.csv` | 訓練 Tier 1 nearby CWA historical model | 六站靠近高雄港周邊，作為港區微氣候近場代理 |
| 高雄站 | `data/raw/observed_hourly/467441.csv` | fallback baseline、快取鍵 freshness 來源之一 | 不再被標成港區核心站 |
| KHWD | `data/raw/observed_hourly/KHWD*.csv` | 即時港區觀測與 port-local 後處理 | 快取鍵已納入 `KHWD*.csv` mtime |
| CWA 官方預報 | `data/config/resolved_cwa_forecast_source.json`、`data/cache/cwa_*` | H1~H4 降雨機率 prior、官方 +3h/+6h 顯示 | JSON 寫入已改用 atomic write |
| 商港海象 | `C4P01/C4Q01/C4Q02/COMC08/46714D` | 波浪、潮位、未來潮汐增水特徵候選 | 歷史資料不足，未進入正式訓練 |

## 3. 模型與融合流程

`predict_dispatch_risk_current()` 會依序組合：

1. 讀取 config 與 model registry。
2. 載入 467441 fallback observations。
3. 嘗試使用 nearby CWA historical model 產生 H1~H4 基礎預測。
4. 在 KHWD 可用時套用港區即時後處理；`no_realtime_khwd_mode=true` 時可停用此路徑做比較。
5. 對降雨機率套用 CWA PoP prior。v1.3 預設為 conservative profile：H1/H2 不套 CWA，H3/H4 以 20% CWA 權重融合；`graduated_like_wind` profile 保留為候選但非預設。
6. 用降雨機率決定雨量是否顯示。`rain_amount_regression.inference_probability_threshold` 目前為 `0.35`，分類訓練門檻仍維持 `0.5`。
7. 回傳派工風險、逐 anchor 數值、官方 CWA 欄位、模型信賴度指標與 trace。

## 4. API 輸入與輸出

### 輸入

| 參數 | 說明 |
|---|---|
| `target_area=KHH` | 高雄港區 |
| `target_station_id` | 可選，指定站點 |
| `no_realtime_khwd_mode=true/false` | 是否停用 KHWD 即時後處理 |
| `refresh_port_local=true/false` | 是否先強制刷新港區即時資料 |

### 主要輸出

| 欄位 | 說明 |
|---|---|
| `model_version` | 目前為 `kaohsiung_port_dispatch_risk_v1.3` |
| `prediction_mode` | 實際使用的模型/後處理模式 |
| `anchors.H1~H4` | 逐時間錨點的風速、陣風、降雨、雨量、風險等級 |
| `cwa` | 前端相容的官方 CWA +3h/+6h 與來源資訊 |
| `metrics` | CSI/POD/FAR 模型信賴度 |
| `metrics.by_horizon` | H1~H4 逐 anchor CSI/POD/FAR |
| `metrics.metrics_report_generated_at` | 指標報表檔案 mtime，讓前端可顯示資料年齡 |
| `trace` | 資料來源、融合權重、後處理與 fallback 記錄 |

## 5. 目前模型指標

指標來源為 nearby CWA 模型評估報表。API 會直接把下列值放到 `/api/v1/dispatch/risk` 的 `metrics` 欄位；若報表不存在，回傳 `available=false` 並以 `null` 表示不偽造數值。

| Horizon | CSI | POD | FAR | 備註 |
|---|---:|---:|---:|---|
| H1 | 0.5524 | 0.6259 | 0.1754 | 目前報表 H1/H2 相同 |
| H2 | 0.5524 | 0.6259 | 0.1754 | 目前報表 H1/H2 相同 |
| H3 | 0.3185 | 0.3597 | 0.2647 | 目前報表 H3/H4 相同 |
| H4 | 0.3185 | 0.3597 | 0.2647 | 目前報表 H3/H4 相同 |

這些數值反映既有 held-out 評估，不代表 API 會在 runtime 自動重訓。v1.3 已移除未被程式讀取的 stale-model 死設定，避免維護者誤以為系統會自動警告 stale model。

## 6. v1.3 近期修正

| 編號 | 變更 |
|---|---|
| 44/46 | 降雨機率 CWA prior 改為可切換 profile，預設退回 conservative，H3/H4 僅 20% CWA 權重 |
| 45 | +3h/+6h 降雨機率改為真正對應目標時間，不再用現在時段代替 |
| 47 | 手動抓取最新資料時會強制刷新 CWA extended forecast 快取 |
| 48/49 | `/api/v1/dispatch/risk` 新增 CSI/POD/FAR，並擴充為 H1~H4 |
| 50 | dispatch risk cache TTL 提高到 120 秒，並改為 per-key singleflight |
| 51 | 雨量顯示門檻由 0.5 調整為 0.35 |
| 52 | 高頻 JSON 寫入改用 `atomic_write_json()` |
| 53 | dispatch risk cache key 納入 `KHWD*.csv` mtime |
| 54 | metrics 回應揭露報表 mtime，並移除死設定 |
| 55 | nearby CWA 六站全失敗時不再被 admin fetch 誤報為成功 |
| 56 | `/cwa/history/diagnostics` 明確標示 `hours` 只套用於 `official_land` |
| 57 | system audit 改用 `predict_dispatch_risk_current` |
| 58/60/61 | 版本字串統一回 v1.3/current 入口，manifest 版本會同步 config |
| 62 | 舊版 v2.5.2 後端總規格書移入 archive |

## 7. 已知限制

1. KHWD 港區資料與商港海象資料仍需持續累積，才能訓練 `port_local_model` 與潮汐增水殘差模型。
2. CWA 歷史預報持續記錄機制仍受資料累積時間限制，暫時不能用來正式比較 PoP prior 權重 profile。
3. 能見度目前以官方來源展示為主，尚未形成完整可訓練模型。
4. QPESUMS 雷達回波資料若要納入 Tier 1 訓練，仍需確認 API 申請、額度與歷史可回溯期間。
5. `metrics` 指標報表不是 runtime 自動重算；需看 `metrics_report_generated_at` 判斷新鮮度。
