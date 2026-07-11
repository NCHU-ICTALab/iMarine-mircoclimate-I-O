# 資料集使用與處理說明（kaohsiung_microclimate_lstm）

本文件說明 `kaohsiung_microclimate_lstm/` 底下的資料從哪裡來、如何被處理成訓練資料集、以及哪些資料有進版控、哪些沒有。目的是讓 clone 這個 repo 的人（含 frontend 整合方）知道：不需要重新訓練也能直接跑 API，若真的要重新訓練，資料要去哪裡拿。

## 1. 資料分層與版控範圍

| 目錄 | 內容 | 是否進 git | 原因 |
| --- | --- | --- | --- |
| `data/raw/historical_weather/` | 6 個鄰近 CWA/CODiS 站的歷史逐時資料（每站約 3 萬筆，2023-01-01 至今） | **否**（`.gitignore` 已排除） | 純訓練用資料，體積較大（約 26MB），且可從公開來源重新下載，不需要放進版控 |
| `data/processed/` | 訓練 pipeline 的中間產物：per-station normalized parquet、聚合後的訓練資料集 parquet、舊版 LSTM baseline 的 npz 檔 | **否**（`.gitignore` 已排除） | 皆可由 `data/raw/historical_weather/` 重新產生，不是原始資料，沒有必要版控 |
| `data/raw/observed_hourly/` | 即時觀測快取：467441 回退站、KHWD 港區風站、O-B0075 海象站、6 站 nearby CWA 即時觀測 | **是** | `predict.py` 在服務請求當下會直接讀取這裡的檔案；保留目前已累積的觀測，讓 clone 下來的服務不用從零開始累積 |
| `data/raw/cwa_forecast_history/` | CWA 預報（F-D0047 系列）每次發布的落地紀錄 | **是** | 體積小（約 1.6MB），且是「持續累積、無法回頭補齊」的歷史紀錄（CWA 不提供歷史發布查詢 API），遺失了就補不回來 |
| `models/` | 訓練好的模型檔（`.joblib`）、`model_manifest.json`、`model_registry.json` | **是** | API 服務直接依賴這些檔案產生預測，是唯一必須隨 repo 一起提供的訓練成果 |
| `results/` | 訓練/評估報告（JSON），如 `nearby_cwa_model_metrics.json`、各版本 `dispatch_risk_v3x/` 報告 | 是 | 體積小，記錄模型指標與稽核結果，供除錯與稽核用途 |

**簡言之**：`models/` 是「已經訓練好、可以直接拿來用的成果」，`data/raw/historical_weather/` 與 `data/processed/` 是「拿來產生上述成果的原料與半成品」。frontend 整合只需要前者，不需要後者。

## 2. 資料來源總覽

| 來源 | 用途 | 對應 Tier（規格書 §1.1） | 如何取得 |
| --- | --- | --- | --- |
| `Raingel/historical_weather`（GitHub） | 6 站鄰近 CWA/CODiS 歷史逐時資料，訓練 `nearby_cwa_historical_model` 骨幹模型 | Tier 1 | `src/tools/backfill_nearby_cwa_historical.py`（見下方指令） |
| CWA Open Data `O-A0001-001` | 即時觀測：467441 回退站、6 站 nearby CWA 即時特徵來源 | Tier 3 / 即時雨量特徵 | `src/data/fetch_nearby_cwa_current.py` |
| CWA Open Data `O-B0075-001` / `O-B0075-002` | 海象即時（48小時）／歷史（30天）：潮位、波高波週期、氣壓、風 | 潮汐增水殘差模型輸入 | `src/data/fetch_marine_history.py` |
| TWPort 即時面板（KHWD/KHTD/KHAW） | 港區風站即時觀測，`port_local_postprocess` 即時安全門檻覆寫的資料來源 | Tier 2 | `src/tools/fetch_port_local_stations.py` |
| CWA Open Data `F-D0047` 系列 | 鄉鎮天氣預報（風速、降雨機率），事後融合用，非模型輸入特徵 | Tier 4 | `src/data/log_cwa_forecast_history.py` |

需要 CWA API Key（`.env` 的 `CWA_API_KEY`）才能呼叫 CWA Open Data 平台，向 [CWA 開放資料平台](https://opendata.cwa.gov.tw/) 申請即可，免費。

## 3. 如何在本地重新取得訓練資料

以下指令皆從專案根目錄執行（PowerShell）：

```powershell
# 1. 下載 6 站鄰近 CWA 歷史逐時資料（訓練骨幹模型用）
python -m kaohsiung_microclimate_lstm.src.tools.backfill_nearby_cwa_historical `
  --station-ids C0V890,C0V490,C0V810,C0V840,C0V450,C0V900 `
  --start-date 20230101 `
  --end-date yesterday

# 2. 抓取港區 KHWD/KHTD/KHAW 即時觀測（累積用，建議排程執行）
python -m kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations

# 3. 抓取海象站即時（O-B0075-001）或 30 天歷史（O-B0075-002）
python -m kaohsiung_microclimate_lstm.src.data.fetch_marine_history --output-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly

# 4. 抓取 6 站 nearby CWA 即時觀測（雨量特徵來源）
python -m kaohsiung_microclimate_lstm.src.data.fetch_nearby_cwa_current
```

執行後，`data/raw/historical_weather/` 與 `data/raw/observed_hourly/` 就會有本地資料可用。

## 4. 資料如何被處理成訓練資料集

```text
data/raw/historical_weather/{station}/*.csv
        │  historical_weather_normalizer.py（欄位正規化：中文/英文欄名統一為 wind_speed、station_pressure 等；
        │  2026-07-11 起同時依 PHYSICAL_RANGE_LIMITS 過濾各變數的物理合理範圍，把來源 CSV 用的缺值代碼
        │  如 -99.x（風速）、-999.6（雨量）轉為 NaN，避免污染下游聚合與訓練標籤）
        ▼
station_frames（正規化後的 per-station DataFrame）
        │  rank_nearby_cwa_stations.py（依與港區距離排序、篩選 Tier 1 候選站）
        ▼
nearby_historical_training_dataset.py::build_nearby_historical_training_dataset()
        │  聚合（跨站 mean/max/min/std）→ 時間特徵 → lag/rolling → labels（H1~H4 各目標）
        ▼
data/processed/nearby_cwa_training_dataset_v32.parquet（聚合後訓練資料集，約 3 萬筆）
        │  train_nearby_cwa_historical_model.py（依 config.yaml 的演算法設定訓練 RandomForest）
        ▼
models/nearby_cwa_v32/*.joblib + model_manifest.json（訓練成果，API 實際使用）
        │  model_registry.py（登記進 model_registry.json，供選模引擎判斷是否已訓練/驗收）
        ▼
models/model_registry.json
```

重新產生聚合訓練資料集與模型的指令：

```powershell
python -m kaohsiung_microclimate_lstm.src.tools.build_nearby_cwa_training_dataset `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --historical-weather-dir kaohsiung_microclimate_lstm/data/raw/historical_weather `
  --output kaohsiung_microclimate_lstm/data/processed/nearby_cwa_training_dataset_v32.parquet `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v32

python -m kaohsiung_microclimate_lstm.src.tools.train_nearby_cwa_historical_model `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --dataset kaohsiung_microclimate_lstm/data/processed/nearby_cwa_training_dataset_v32.parquet `
  --output-dir kaohsiung_microclimate_lstm/models/nearby_cwa_v32 `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v32
```

## 5. 目前已知的資料限制（供 frontend 整合時參考）

- `port_local_model`（KHWD 港區局地 ML 模型）尚未訓練：需要 KHWD 累積至少 500 筆／14 天觀測，目前仍在累積中，實際使用的是規則式的 `port_local_postprocess`，不是這個 ML 模型。
- CWA 歷史預報比較（本模型 vs. 氣象局）需要至少 14 天的持續發布記錄，目前仍在累積，尚無法產出比較報告。
- 降雨量（mm）回歸與潮汐增水殘差模型的 R² 目前偏弱（已知限制，非 bug），詳見 `docs/spec_v13_implementation_summary.md`。
