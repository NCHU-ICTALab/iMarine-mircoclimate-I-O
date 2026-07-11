# 目前微氣候模型、資料來源、資料量、成效與輸出整理

更新日期：2026-07-11（風速/雨量指標已隨資料清理與重訓更新，其餘章節仍為 2026-07-09 版本內容）  
版本：`kaohsiung_port_dispatch_risk_v3.5`  
目標區域：高雄港 `KHH`

本文件依據目前專案內 v3.5 報表整理：

- `kaohsiung_microclimate_lstm/results/dispatch_risk_v35/system_audit_report.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_accuracy_summary_report.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v35/dataset_duration_report.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v35/model_selection_summary_report.json`
- `kaohsiung_microclimate_lstm/results/dispatch_risk_v35/prediction_samples_v35.json`

## 1. 目前整體狀態

目前系統狀態為 `ready_for_demo_and_operation`。一般情境下，API 會優先使用高雄港港區 KHWD 即時風力資料做 `port_local_postprocess`，也就是以港區即時測站資料修正或確認風速、陣風風險。

目前正式已訓練且通過驗收的模型是 `nearby_cwa_historical_model`，資料來源為高雄港周邊 CWA/CODIS 歷史測站。這個模型在 KHWD 即時資料不可用時，會作為備援模型使用。

`port_local_model` 目前未啟用，原因是 KHWD 歷史訓練資料尚不足，還不能訓練成正式港區本地模型。`467441` 高雄氣象站目前只保留為最後備援資料，不作為核心測站。

目前模式選擇如下：

| 情境 | 選用模式 | 風速來源 | 陣風來源 | 是否 fallback 到 467441 |
| --- | --- | --- | --- | --- |
| 一般模式 | `port_local_postprocess` | KHWD | KHWD | 否 |
| 無 KHWD 即時資料 | `nearby_cwa_historical_model` | nearby CWA historical model | nearby CWA historical model | 否 |
| 最後備援 | `fallback_baseline` | 467441 | 467441 | 只有前兩者都不可用才會使用 |

## 2. 各指標目前使用的模型與資料來源

| 指標 | 目前主要方法 | 預設資料來源 | 備援資料來源 | 目前狀態 |
| --- | --- | --- | --- | --- |
| 平均風速 `wind_speed` | `port_local_postprocess`，以 KHWD 即時資料做港區本地後處理 | KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08 | `nearby_cwa_historical_model`，最後才是 467441 | 可用 |
| 最大陣風 `wind_gust` | `port_local_postprocess`，以 KHWD 即時資料做港區本地後處理 | KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08 | `nearby_cwa_historical_model`，最後才是 467441 | 可用 |
| 降雨機率 `rain_probability` | `nearby_cwa_historical_rain_model_plus_cwa_prior` | nearby CWA 歷史測站模型，加上 CWA 前鎮 3 小時 PoP 作為後處理 prior | 模型不可用時才會退回基準邏輯 | 可用，但信心等級目前為 `low_to_medium` |
| 派工風險 `dispatch_risk_level` | 規則式聚合，取雨、風速、陣風、能見度、潮位等風險等級中的最高等級 | 風速/陣風來自 KHWD，雨量機率來自模型與 CWA PoP prior | 視各指標可用性 fallback | 可用 |
| 派工建議 `dispatch_action_level` | 規則式 mapping | `dispatch_risk_level` 與觸發原因 | 無 | 可用 |
| 潮位 `tide` | 目前在 dispatch API 中為參考性欄位 | 無即時核心輸入 | 既有 harmonic/tide 模型檔可作歷史或離線參考 | 目前 API 顯示 `reference_only`，不作主要派工判斷 |
| 能見度 `visibility` | 目前未接入有效資料 | 無 | 無 | 目前 API 顯示 `unavailable` 或 `optional` |

重要限制：

- CWA PoP 只作為降雨機率後處理 prior，不作為模型訓練輸入。
- nearby CWA 歷史測站不是 port-local core station，只是備援訓練參考。
- 467441 沒有被當作核心測站，目前 `467441_used_as_core_station = false`。

## 3. 目前預設資料來源與使用資料量

| 資料集 | 角色 | 測站 | 時間範圍 | 總筆數 | 有效筆數 | 有效率 | 是否用於訓練 | 是否用於目前預測 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| KHWD port-local realtime station data | 港區即時後處理 | KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08 | 2026-07-08 23:27 至 2026-07-08 23:29 | 12 | 12 | 1.0000 | 否 | 是 |
| Nearby CWA historical training dataset | 備援歷史模型訓練 | C0V890、C0V490、C0V840、C0V810、C0V450、C0V900 | 報表以總天數統計，約 1282 天 | 184614 | 184385 | 0.9988 | 是 | 一般模式否；無 KHWD 時是 |
| 467441 fallback baseline data | 最後備援 | 467441 | 2026-01-07 01:00 至 2026-07-05 23:00 | 4144 | 4144 | 1.0000 | 否 | 否 |

### 3.1 每筆資料的時間間隔與尺度

| 資料來源 | 每筆資料代表什麼 | 原始時間間隔 | 目前資料尺度 | 進入系統後的使用方式 |
| --- | --- | --- | --- | --- |
| KHWD port-local realtime | 單一 KHWD 港區風力站在某一觀測時間的即時風速、風向、陣風 | 即時頁面快照，實際資料以分鐘時間戳記呈現；目前本機資料為 2026-07-08 23:27 到 23:29 的短時間快照 | 港區測站尺度，station-level；每筆是單一測站資料 | 不作訓練；先取各 KHWD 測站最新值，再聚合成 `khwd_wind_speed_max`、`khwd_wind_gust_max`，用於 `port_local_postprocess` |
| Nearby CWA/CODIS historical | 單一 CWA/CODIS 周邊測站在某一小時的歷史觀測 | 1 小時；實際 parquet 檔為 hourly observation | 周邊測站尺度，station-level；訓練時再聚合成多測站特徵 | 用於訓練 `nearby_cwa_historical_model`；會依 `obs_time` 聚合同一時間的多站風速、陣風、雨量等特徵 |
| 467441 fallback baseline | 467441 高雄氣象站在某一小時的歷史觀測 | 主要為 1 小時；本機資料中少量 2 小時間隔或重複時間點 | 單一 CWA 測站尺度，station-level | 只作最後備援 baseline，不作目前核心測站，也不作目前一般模式輸入 |
| CWA PoP 前鎮區 | CWA 預報區間內的降雨機率 | 3 小時預報區間，`source_resolution = 3h` | 行政區/預報區尺度，不是港區測站尺度 | 不作模型訓練輸入；只作為 `rain_probability` 的後處理 prior，並對齊 H1~H4 錨點 |
| H1~H4 forecast anchors | 派工 API 輸出的未來預測時間點 | H1=30 分鐘、H2=60 分鐘、H3=90 分鐘、H4=120 分鐘 | 派工決策時間尺度 | 每個 anchor 各自輸出雨、風速、陣風、風險等級與派工建議 |

補充說明：

- KHWD 目前抓到的是即時快照資料，不是連續長期歷史資料；因此足夠做「當下風險覆核」，但不足以訓練正式 `port_local_model`。
- nearby CWA 歷史資料是目前真正用來訓練模型的主要資料來源，時間粒度是 hourly。
- CWA PoP 的尺度較粗，屬於 3 小時預報區間與區域性預報，所以只作降雨機率 prior，不直接當作港區測站觀測。
- API 輸出的 H1~H4 是派工決策尺度，不一定等於原始資料時間粒度；系統會把 hourly 或 3h 資料對齊到這些 anchor。

### 3.2 模型訓練需要多少歷史資料

目前專案內有兩個主要訓練門檻：一個是未來要啟用的港區本地模型 `port_local_model`，另一個是目前已訓練完成的 `nearby_cwa_historical_model`。

| 模型 | 訓練資料來源 | 最低資料量門檻 | 最低時間跨度 | 其他必要條件 | 目前是否達標 |
| --- | --- | ---: | ---: | --- | --- |
| `port_local_model` | KHWD 港區測站歷史資料 | 500 筆聚合後樣本 | 14 天 | 每個 horizon H1~H4 至少 100 筆有效 label；feature missing ratio 不得超過 0.30；label missing ratio 不得超過 0.30 | 否 |
| `nearby_cwa_historical_model` | nearby CWA/CODIS 歷史測站 | 1000 筆 station-hour 樣本 | 30 天 | 至少 2 個可用測站；有效 wind samples >= 500；有效 gust samples >= 500；有效 rain samples >= 500 | 是 |
| 舊版 LSTM baseline | 467441、C4Q01、C4Q02、1786 等歷史資料 | 目前設定檔沒有獨立 readiness 門檻 | 依資料切分與 `min_valid_ratio=0.70` | 使用 train/val/test = 70/15/15；time step 為 10 分鐘、lookback 為 12 小時 | 已有舊 checkpoint，但不是 v3.5 正常模式主模型 |

`port_local_model` 的「500 筆」不是指 raw CSV 中每個測站各 500 筆，而是資料建模後依時間聚合出的訓練列數。每一列代表一個觀測時間點的港區多測站特徵，例如 KHWD 多站風速平均、最大值、陣風最大值、風向 sin/cos、rolling features 等。

以時間尺度估算：

| 資料粒度 | 達到 500 筆大約需要多久 | 是否滿足 14 天最低跨度 |
| --- | ---: | --- |
| 1 小時一筆 | 約 500 小時，約 20.8 天 | 是 |
| 10 分鐘一筆 | 約 83.3 小時，約 3.5 天 | 否，仍需至少跨 14 天 |
| 1 分鐘一筆 | 約 8.3 小時 | 否，仍需至少跨 14 天 |

所以對 `port_local_model` 來說，實務上最少要累積「跨 14 天以上」且「聚合後至少 500 個時間點」的 KHWD 歷史資料，並且 H1、H2、H3、H4 都要有足夠未來 label。若用 1 小時資料，約 21 天以上會比較穩；若用更細的 10 分鐘或 1 分鐘資料，筆數會更快達標，但時間跨度仍不能少於 14 天。

目前 KHWD 的現況：

- raw KHWD CSV 已有 KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08。
- 目前 v3.5 報表中的 KHWD 即時資料只有 12 筆 raw records。
- 建模後 `port_local_training_dataset` 的 readiness 曾顯示 sample_count 僅 3，training_days 約 0.001 天。
- 因此目前 KHWD 資料足夠做 `port_local_postprocess`，但遠低於 `port_local_model` 訓練門檻。

目前 nearby CWA 的現況：

- 訓練資料共 184614 筆 station-hour records。
- 有效資料 184385 筆。
- 跨度約 1282 天。
- 已明顯超過最低門檻，因此 `nearby_cwa_historical_model` 已能訓練並通過驗收。

## 4. 目前模型成效

### 4.1 港區本地模型 `port_local_model`

| 項目 | 狀態 |
| --- | --- |
| 是否訓練完成 | 否 |
| 是否可用 | 否 |
| 是否通過驗收 | 否 |
| 原因 | KHWD 歷史資料尚未達到訓練需求 |
| 是否有準確度數據 | 否 |

### 4.2 周邊 CWA 歷史備援模型 `nearby_cwa_historical_model`

這是目前已訓練、可用且通過驗收的模型。訓練測站為 C0V890、C0V490、C0V840、C0V810、C0V450、C0V900。

#### 平均風速 `wind_speed`

單位：m/s。MAE、RMSE 越低越好，R2 越高越好。

| 預測錨點 | MAE | RMSE | R2 | Bias | critical under-warning |
| --- | ---: | ---: | ---: | ---: | ---: |
| H1 | 0.5512 | 0.7803 | 0.7625 | -0.0488 | 0 |
| H2 | 0.5513 | 0.7804 | 0.7625 | -0.0488 | 0 |
| H3 | 0.6786 | 0.9669 | 0.6354 | -0.0874 | 0 |
| H4 | 0.6786 | 0.9669 | 0.6354 | -0.0873 | 0 |

判讀：2026-07-11 從資料源頭清除了風速缺值代碼污染（原始 CSV 用 `-99.x` 代表缺值，未被過濾）後重新訓練，R2 從 0.33~0.37 大幅提升到 0.64~0.76，短期 H1/H2 平均誤差降到約 0.55 m/s，H3/H4 約 0.68 m/s，準確度已明顯優於清理前。

#### 最大陣風 `wind_gust`

單位：m/s。MAE、RMSE 越低越好，R2 越高越好。

| 預測錨點 | MAE | RMSE | R2 | Bias | critical under-warning |
| --- | ---: | ---: | ---: | ---: | ---: |
| H1 | 0.6809 | 0.9556 | 0.8542 | 0.0725 | 0 |
| H2 | 0.6809 | 0.9557 | 0.8542 | 0.0724 | 0 |
| H3 | 0.9457 | 1.3330 | 0.7163 | 0.0154 | 0 |
| H4 | 0.9458 | 1.3331 | 0.7163 | 0.0152 | 0 |

判讀：陣風原始資料就沒有缺值代碼污染問題，本來就是表現最穩定的變數，資料清理後 H1/H2 的 R2 約 0.85，H3/H4 約 0.72，跟清理前幾乎持平；目前沒有重大低估警示案例，適合做派工風險參考。

#### 降雨機率 `rain_probability`

Brier score 越低越好；POD、AUC、CSI 越高越好；FAR 越低越好。

| 預測錨點 | Brier score | POD | FAR | AUC | CSI |
| --- | ---: | ---: | ---: | ---: | ---: |
| H1 | 0.0183 | 0.6259 | 0.1754 | 0.9546 | 0.5524 |
| H2 | 0.0183 | 0.6259 | 0.1754 | 0.9546 | 0.5524 |
| H3 | 0.0263 | 0.3597 | 0.2647 | 0.9322 | 0.3185 |
| H4 | 0.0263 | 0.3597 | 0.2647 | 0.9322 | 0.3185 |

判讀：H1/H2 的降雨機率表現較佳，AUC 約 0.95，Brier score 約 0.018。H3/H4 仍可用，但 POD 和 CSI 明顯下降，因此較適合作為風險提醒，不建議單獨用來做硬性派工取消決策。

另外，2026-07-11 已完成雨量量值（mm）回歸模型的資料清理與 log1p 目標轉換：`precipitation_amount` H1 R2 從 -0.11（幾乎無預測力）提升到 0.45，H3 從 -0.13 提升到 0.26，詳見規格書第 15 節與 `docs/spec_v13_implementation_summary.md`。

## 5. API 目前輸出的結果

主要 endpoint：

- `/api/v1/dispatch/risk`
- `/api/v1/dispatch/model-status`
- `/api/v1/dispatch/station-usage`
- `/api/v1/dispatch/system-audit`
- `/dispatch-risk-demo`

`/api/v1/dispatch/risk` 主要輸出內容包含：

| 欄位 | 說明 |
| --- | --- |
| `model_version` | 模型/系統版本，目前為 `kaohsiung_port_dispatch_risk_v3.5` |
| `prediction_mode` | 本次選用模式，例如 `port_local_postprocess` |
| `forecast_anchors` | H1 到 H4 預測錨點，每個錨點包含雨、風速、陣風、風險與派工建議 |
| `rain.final_probability` | 最終降雨機率 |
| `rain.level` | 降雨風險等級 |
| `rain.confidence` | 降雨預測信心 |
| `wind_speed.predicted_mps` | 預測平均風速，單位 m/s |
| `wind_speed.operation_level` | 風速對應作業風險等級 |
| `wind_gust.predicted_mps` | 預測最大陣風，單位 m/s |
| `wind_gust.operation_level` | 陣風對應作業風險等級 |
| `dispatch_risk_level` | 綜合派工風險等級 |
| `dispatch_action_level` | 派工行動等級，例如正常派工、觀察、延後或停止 |
| `risk_trigger_detail` | 主要觸發因子與各指標風險等級 |
| `dispatch_suggestion` | 給前端顯示的派工建議文字 |
| `current_station_usage` | 本次使用哪些測站與資料來源 |
| `station_display_rows` | 前端可直接顯示的測站清單與角色 |
| `model_selection_summary` | 模型選擇原因、fallback chain、被擋下的模式原因 |
| `model_training_status` | 模型訓練與 registry 狀態 |
| `data_availability` | KHWD、CWA PoP、潮位、能見度等資料可用狀態 |
| `system_audit_summary` | 系統稽核摘要 |

目前 H1 到 H4 的時間間隔設定：

| 錨點 | offset |
| --- | ---: |
| H1 | 30 分鐘 |
| H2 | 60 分鐘 |
| H3 | 90 分鐘 |
| H4 | 120 分鐘 |

## 6. 目前可作為派工參考的程度

目前可作為派工參考，尤其是陣風與短期降雨風險。不過應定位為「風險輔助決策」，而不是完全自動化派工決策。

較可靠的部分：

- KHWD 港區即時風力資料已可用於目前派工風速與陣風後處理。
- 陣風模型在 nearby CWA 備援模式下表現較好，H1/H2 MAE 約 0.68 m/s，R2 約 0.85。
- 降雨 H1/H2 AUC 約 0.96，Brier score 約 0.018，短期降雨風險可作參考。
- 系統目前沒有把 467441 當作核心測站。

需要注意的部分：

- 港區本地 KHWD 模型尚未正式訓練完成，因為 KHWD 歷史資料不足。
- 平均風速 R2 約 0.33 到 0.37，數值準確度普通，較適合轉成風險等級使用。
- 降雨 H3/H4 的 POD 和 CSI 較低，長一點的預測只能作預警參考。
- 潮位與能見度目前沒有作為主要派工決策條件。

## 7. 結論

目前版本的核心派工輸出可以放到前端展示。前端最適合顯示：

- 目前選用模式：`port_local_postprocess`
- 使用測站：KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08
- H1 到 H4 的降雨機率、平均風速、最大陣風、綜合風險等級、派工建議
- 模型狀態：nearby CWA historical model 已訓練且通過驗收，port-local model 尚未就緒
- 安全稽核：467441 未作為核心測站、CWA PoP 未作為模型輸入、降雨機率有保留並作後處理

若後續要讓系統從「可展示/可輔助」提升到「可正式作業依據」，下一步重點是累積 KHWD 港區歷史資料，讓 `port_local_model` 能正式訓練並通過驗收。

## 8. 各指標使用的模型種類

下表補充「模型種類」，並區分目前 v3.5 API 實際使用的方式，以及專案中仍保留的舊版 LSTM checkpoint。派工 API 目前不是單純全部走 LSTM；v3.5 的主要流程是 KHWD 港區即時後處理優先，KHWD 不可用時才使用 nearby CWA historical model。

| 指標 | 目前 v3.5 API 實際使用的模型種類 | 訓練狀態 | 對應模型/檔案 | 備註 |
| --- | --- | --- | --- | --- |
| 平均風速 `wind_speed` | 一般模式：規則式 `port_local_postprocess`；KHWD 不可用時：`RandomForestRegressor` | nearby CWA 模型已訓練；port-local model 未訓練成功 | `nearby_cwa_v32/wind_speed_H1~H4.joblib` | Random Forest 參數為 `n_estimators=80`、`min_samples_leaf=2`、`random_state=42` |
| 最大陣風 `wind_gust` | 一般模式：規則式 `port_local_postprocess`；KHWD 不可用時：`RandomForestRegressor` | nearby CWA 模型已訓練；port-local model 未訓練成功 | `nearby_cwa_v32/wind_gust_H1~H4.joblib` | 與平均風速相同，使用 Random Forest 回歸模型 |
| 降雨機率 `rain_probability` | `RandomForestClassifier` 加 CWA PoP 後處理 prior | nearby CWA 降雨模型已訓練 | `nearby_cwa_v32/rain_probability_H1~H4.joblib` | CWA PoP 不是訓練輸入，只在模型輸出後作 prior/blending |
| 派工風險 `dispatch_risk_level` | 無 ML 訓練模型，使用規則式 max-level aggregation | 不需訓練 | `dispatch_risk_aggregator` 規則 | 取雨、風速、陣風、能見度、潮位等級中的最高風險 |
| 派工行動 `dispatch_action_level` | 無 ML 訓練模型，使用規則式 action mapping | 不需訓練 | `action_mapping` 規則 | 由 `dispatch_risk_level` 對應派工建議 |
| 潮位 `tide` | API 目前為 `reference_only`；離線保存有 harmonic model 與 LSTM checkpoint | harmonic model 已有保存；不作目前主要派工判斷 | `models/tide/*_harmonic_coef.pkl`、`models/checkpoints/*_tide_level_best.pt` | harmonic 為調和分析模型；舊版 tide checkpoint 的 `model_type` 為 `lstm` |
| 能見度 `visibility` | 無模型 | 未接入 | 無 | 目前 API 為 `unavailable` 或 `optional` |

### 8.1 一般模式 `port_local_postprocess` 是什麼模型

`port_local_postprocess` 不是經過訓練的 ML 模型，也不是 LSTM、Random Forest 或神經網路。它是規則式後處理模型，也可以稱為 rule-based threshold postprocessor。

目前一般模式下，系統先取得可用的 KHWD 港區即時風力站資料，再用這些即時值修正風速與陣風的作業風險等級。它的邏輯是「港區即時觀測優先」：如果 KHWD 即時觀測已經達到警戒門檻，就算基礎預測模型風險較低，也會把派工風險往上調。

目前使用的 KHWD 測站：

- KHWD01
- KHWD04
- KHWD05
- KHWD06
- KHWD07
- KHWD08

`port_local_postprocess` 使用的主要特徵：

| 特徵 | 說明 | 用途 |
| --- | --- | --- |
| `khwd_wind_speed_max` | KHWD 多測站即時平均風速最大值 | 判斷平均風速是否觸發 warning、high_risk、stop |
| `khwd_wind_gust_max` | KHWD 多測站即時最大陣風最大值 | 判斷陣風是否觸發 warning、high_risk、stop |
| `station_ids_used` | 本次實際使用的 KHWD 測站清單 | 輸出 trace 與前端顯示 |

風速後處理邏輯：

1. 讀取基礎預測或目前基礎風險等級，例如 `normal`、`watch`、`warning`。
2. 讀取 KHWD 即時 `khwd_wind_speed_max`。
3. 對照 `wind_speed.thresholds_mps` 中的 `warning`、`high_risk`、`stop` 門檻。
4. 如果 KHWD 觸發的等級高於基礎等級，輸出較高等級。
5. 如果 KHWD 未超過門檻，維持原本基礎等級。

陣風後處理邏輯：

1. 讀取基礎陣風風險等級。
2. 讀取 KHWD 即時 `khwd_wind_gust_max`。
3. 對照 `wind_gust.thresholds_mps` 中的 `warning`、`high_risk`、`stop` 門檻。
4. 如果 KHWD 觸發的等級高於基礎等級，輸出較高等級。
5. 如果 KHWD 未超過門檻，維持原本基礎等級。

因此它的模型種類可整理為：

| 項目 | 說明 |
| --- | --- |
| 模型種類 | 規則式門檻後處理模型 |
| 英文描述 | rule-based threshold postprocessor |
| 是否需要訓練 | 否 |
| 是否有權重檔 | 否 |
| 是否使用 KHWD 即時資料 | 是 |
| 是否使用 467441 | 否 |
| 是否會降低風險 | 否，只會維持原風險或提高風險 |
| 主要目的 | 避免模型低估港區當下局部強風或陣風 |

目前可以把 `port_local_postprocess` 視為「港區即時安全覆核層」，不是預測模型本體。它讓系統在港區 KHWD 即時資料可用時，優先反映高雄港當下真實風況。

### 8.2 目前正式可用的 Random Forest 模型

目前正式可用、且進入 model registry/selection 的訓練模型是 `nearby_cwa_historical_model`：

| 指標 | 模型種類 | 任務類型 | 輸出 |
| --- | --- | --- | --- |
| `wind_speed` | `sklearn.ensemble.RandomForestRegressor` | 回歸 | H1~H4 平均風速，單位 m/s |
| `wind_gust` | `sklearn.ensemble.RandomForestRegressor` | 回歸 | H1~H4 最大陣風，單位 m/s |
| `rain_probability` | `sklearn.ensemble.RandomForestClassifier` | 二元分類/機率預測 | H1~H4 降雨事件機率 |

訓練資料為 nearby CWA/CODIS 歷史測站 C0V890、C0V490、C0V840、C0V810、C0V450、C0V900，共 184614 筆，1282 天；有效資料 184385 筆。

### 8.3 尚未正式啟用的 port-local 模型

`port_local_model` 的訓練程式目前設計為：

| 指標 | 預定模型種類 | 狀態 |
| --- | --- | --- |
| `wind_speed` | `RandomForestRegressor` | KHWD 歷史資料不足，未通過 readiness，未正式啟用 |
| `wind_gust` | `RandomForestRegressor` | KHWD 歷史資料不足，未通過 readiness，未正式啟用 |
| `rain_probability` | 目前沒有啟用 port-local rain model | 沿用 nearby CWA rain model 加 CWA PoP prior |

也就是說，現在的 KHWD 港區資料主要用於即時後處理，不是已訓練完成的 port-local ML 模型。

### 8.4 專案中保留的舊版 LSTM checkpoint

專案仍保留舊版 LSTM checkpoint，可作為歷史基線或離線比較，但不是 v3.5 正常模式下的主要模型選擇。

| 指標/資料 | 模型種類 | checkpoint 範例 |
| --- | --- | --- |
| 467441 降雨 | `twostage_lstm` | `models/checkpoints/467441_precipitation_best.pt` |
| 467441 風速/陣風 | `multitask_lstm` | `models/checkpoints/467441_wind_speed_gust_best.pt` |
| C4Q01、C4Q02 風速/陣風 | `multitask_lstm` | `models/checkpoints/C4Q01_wind_speed_gust_best.pt`、`models/checkpoints/C4Q02_wind_speed_gust_best.pt` |
| 1786、C4P01、C4Q01、C4Q02 潮位 | `lstm` | `models/checkpoints/*_tide_level_best.pt` |

LSTM 架構種類說明：

- `lstm`：單一輸出頭的 Baseline LSTM，用於一般連續值預測，例如潮位。
- `multitask_lstm`：共用 LSTM encoder，分別輸出 wind speed 與 wind gust。
- `twostage_lstm`：降雨兩階段模型，同時輸出降雨事件機率與雨量，其中分類部分使用 focal loss。
- `spatial_lstm`：多測站空間模型架構已保留在程式中，但目前不是 v3.5 正式啟用模型。

## 9. 各模型的輸入資料

本節整理「模型或決策層實際吃進去的輸入」。其中 `port_local_postprocess` 和派工風險聚合不是訓練模型，但它們仍有明確輸入。

### 9.1 `port_local_postprocess` 輸入

`port_local_postprocess` 使用 KHWD 港區即時資料，不吃歷史訓練 feature，也沒有權重檔。

| 輸入 | 來源 | 說明 |
| --- | --- | --- |
| `khwd_wind_speed_max` | KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08 | 多個 KHWD 站最新平均風速中的最大值 |
| `khwd_wind_gust_max` | KHWD01、KHWD04、KHWD05、KHWD06、KHWD07、KHWD08 | 多個 KHWD 站最新陣風中的最大值 |
| `station_ids_used` | KHWD 可用測站清單 | 用於 trace 與前端顯示 |
| `wind_speed.thresholds_mps` | `config.yaml` | 平均風速 warning、high_risk、stop 門檻 |
| `wind_gust.thresholds_mps` | `config.yaml` | 陣風 warning、high_risk、stop 門檻 |
| base operation level | 基礎預測或原始風險等級 | 後處理只會維持或提高風險，不會降低風險 |

### 9.2 `nearby_cwa_historical_model` 輸入

目前正式可用的 `nearby_cwa_historical_model` 使用 34 個 feature。風速、陣風、降雨機率三種 Random Forest 模型使用同一組 feature，但 label 不同。

| 模型輸出 | 模型種類 | 輸入 feature 數 | label |
| --- | --- | ---: | --- |
| `wind_speed_H1~H4` | `RandomForestRegressor` | 34 | `target_nearby_wind_speed_H1~H4` |
| `wind_gust_H1~H4` | `RandomForestRegressor` | 34 | `target_nearby_wind_gust_H1~H4` |
| `rain_probability_H1~H4` | `RandomForestClassifier` | 34 | `target_rain_event_H1~H4` |

完整輸入 feature：

| 類別 | feature |
| --- | --- |
| 測站數量 | `nearby_cwa_station_count` |
| 平均風速統計 | `nearby_cwa_wind_speed_mean`、`nearby_cwa_wind_speed_max`、`nearby_cwa_wind_speed_min`、`nearby_cwa_wind_speed_std`、`nearby_cwa_valid_wind_station_count` |
| 陣風統計 | `nearby_cwa_wind_gust_mean`、`nearby_cwa_wind_gust_max`、`nearby_cwa_wind_gust_min`、`nearby_cwa_wind_gust_std`、`nearby_cwa_valid_gust_station_count` |
| 雨量統計 | `nearby_cwa_precipitation_1hr_mean`、`nearby_cwa_precipitation_1hr_max`、`nearby_cwa_rainy_station_count`、`nearby_cwa_rainy_station_ratio` |
| 風向向量 | `nearby_cwa_wind_direction_sin_mean`、`nearby_cwa_wind_direction_cos_mean`、`nearby_cwa_gust_direction_sin_mean`、`nearby_cwa_gust_direction_cos_mean` |
| 距離加權 | `distance_weighted_wind_speed`、`distance_weighted_wind_gust`、`distance_weighted_precipitation` |
| 時間週期 | `hour_sin`、`hour_cos`、`doy_sin`、`doy_cos` |
| lag/rolling | `nearby_cwa_wind_speed_max_lag1`、`nearby_cwa_wind_speed_max_roll3`、`nearby_cwa_wind_gust_max_lag1`、`nearby_cwa_wind_gust_max_roll3`、`nearby_cwa_precipitation_1hr_max_lag1`、`nearby_cwa_precipitation_1hr_max_roll3`、`nearby_cwa_precipitation_roll3`、`nearby_cwa_precipitation_roll6` |

注意：CWA PoP 不在這 34 個 model input 中。CWA PoP 只在模型輸出後，用於 `rain_probability` 的 prior/postprocess。

### 9.3 尚未啟用的 `port_local_model` 預定輸入

`port_local_model` 目前未通過 readiness，因此不是正式啟用模型。但建模資料表已定義 30 個 KHWD feature。

| 模型輸出 | 預定模型種類 | 輸入 feature 數 | label |
| --- | --- | ---: | --- |
| `wind_speed_H1~H4` | `RandomForestRegressor` | 30 | `target_wind_speed_H1~H4` |
| `wind_gust_H1~H4` | `RandomForestRegressor` | 30 | `target_wind_gust_H1~H4` |

預定輸入 feature：

| 類別 | feature |
| --- | --- |
| KHWD 平均風速統計 | `khwd_wind_speed_mean`、`khwd_wind_speed_max`、`khwd_wind_speed_min`、`khwd_wind_speed_std`、`khwd_wind_speed_range` |
| KHWD 陣風統計 | `khwd_wind_gust_mean`、`khwd_wind_gust_max`、`khwd_wind_gust_min`、`khwd_wind_gust_std`、`khwd_wind_gust_range` |
| 測站數量 | `khwd_station_count`、`khwd_valid_wind_station_count`、`khwd_valid_gust_station_count` |
| 風向向量 | `khwd_wind_direction_sin_mean`、`khwd_wind_direction_cos_mean`、`khwd_gust_direction_sin_mean`、`khwd_gust_direction_cos_mean` |
| 時間週期 | `hour_sin`、`hour_cos`、`doy_sin`、`doy_cos` |
| lag/rolling | `khwd_wind_speed_mean_lag1`、`khwd_wind_speed_mean_lag2`、`khwd_wind_speed_max_lag1`、`khwd_wind_gust_max_lag1`、`khwd_wind_gust_max_lag2`、`khwd_wind_speed_mean_roll3`、`khwd_wind_speed_max_roll3`、`khwd_wind_gust_mean_roll3`、`khwd_wind_gust_max_roll3` |

目前這組 feature 只有 3 筆建模樣本，還不能訓練正式 port-local 模型。

### 9.4 舊版 LSTM baseline 輸入

舊版 LSTM checkpoint 仍保留，但不是 v3.5 正常模式的主模型。其輸入是時間序列 window，設定為：

| 項目 | 設定 |
| --- | --- |
| `time_step_minutes` | 10 分鐘 |
| `lookback_hours` | 12 小時 |
| anchor | H1=30 分鐘、H2=60 分鐘、H3=90 分鐘、H4=120 分鐘 |
| 一般 LSTM feature 數 | wind/rain checkpoint 為 11 features；tide checkpoint 為 10 features |

依 `config.yaml` 的舊版 feature 設定，target-station 類輸入包含：

- `wind_speed`
- `wind_gust`
- `precipitation_1hr`
- `wind_dir_sin`
- `wind_dir_cos`
- `hour_sin`
- `hour_cos`
- `doy_sin`
- `doy_cos`
- `tide_sin`
- `tide_cos`

舊版 LSTM 對應：

| 模型 | 模型種類 | 主要輸入 | 輸出 |
| --- | --- | --- | --- |
| 467441 wind/gust baseline | `multitask_lstm` | 467441 target-station 時序特徵 | H1~H4 `wind_speed`、`wind_gust` |
| 467441 rain baseline | `twostage_lstm` | 467441 target-station 時序特徵 | H1~H4 降雨機率與雨量 |
| tide baseline | `lstm` 或 harmonic | 潮位相關時序/調和特徵 | H1~H4 潮位 |

### 9.5 派工風險聚合輸入

`dispatch_risk_level` 不是訓練模型，它吃的是各指標已轉換後的風險等級。

| 輸入 | 來源 |
| --- | --- |
| `rain.level` | 降雨機率模型與 CWA PoP prior 後處理 |
| `wind_speed.operation_level` | 風速模型或 KHWD postprocess |
| `wind_gust.operation_level` | 陣風模型或 KHWD postprocess |
| `visibility.level` | 目前未接入，通常為 null |
| `tide.level` | 目前參考用，通常不作主要派工條件 |

聚合規則是 max-level rule：取所有可用指標中風險最高的等級，並輸出 `risk_trigger_detail` 和 `dispatch_action_level`。
