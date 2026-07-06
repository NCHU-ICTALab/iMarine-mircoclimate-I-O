# 高雄港微氣候 LSTM Baseline

這個子專案依照 `高雄港微氣候_LSTM_Baseline規格書.md` 實作一套可訓練、可評估、可推論的 PyTorch LSTM baseline。它和既有 FastAPI 資料擷取服務分開放置，避免影響目前 API。

## 功能範圍

- 支援 CSV / Parquet 歷史觀測資料。
- 以單測站獨立建模，針對不同目標群組訓練模型。
- 預測 H1-H4 四個錨點：+30、+60、+90、+120 分鐘。
- 內建資料前處理、缺值策略、循環特徵、MinMaxScaler、滑動窗口切割。
- 提供三種模型：
  - `lstm`：潮位、能見度等單目標回歸。
  - `multitask_lstm`：風速與陣風共用 encoder，多任務輸出。
  - `twostage_lstm`：降雨分類頭加雨量回歸頭。
- 評估會輸出 MAE、RMSE、MAPE、R2、Bias、降雨 CSI/FAR、Persistence baseline 比較與 `accuracy_grade`。
- 推論介面會輸出可供排程或前端使用的 H1-H4 anchors JSON。

## 安裝

```powershell
cd kaohsiung_microclimate_lstm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 輸入資料格式

輸入檔案需為 CSV 或 Parquet，至少包含：

- `station_id`
- `obs_time`
- `wind_speed`
- `wind_gust`
- `wind_direction`
- `precipitation_1hr`
- `tide_level`
- `visibility`，可選

也支援既有 API 欄位別名：

- `wind_speed_mps` -> `wind_speed`
- `wind_gust_mps` -> `wind_gust`
- `wind_direction_deg` -> `wind_direction`
- `precipitation_1hr_mm` -> `precipitation_1hr`
- `visibility_m` -> `visibility`

## 訓練單一模型

```powershell
python src/train.py --station_id 高雄港 --target tide_level --config config.yaml --data_path data/raw/高雄港.csv
```

`--target` 對應 `config.yaml` 的 target key：

- `wind_speed_gust`
- `precipitation`
- `tide_level`
- `visibility`

訓練完成後會自動執行評估，並輸出：

- `data/processed/{station_id}_{target}.npz`
- `data/processed/data_quality_report.json`
- `scalers/{station_id}_{target}_scaler.pkl`
- `models/checkpoints/{station_id}_{target}_best.pt`
- `logs/training/{station_id}_{target}.json`
- `results/evaluation/{station_id}_{target}_metrics.json`
- `results/evaluation/summary_report.csv`

## 批次訓練

```powershell
python run_all.py --data_dir data/raw --config config.yaml
```

此指令會掃描 `data/raw` 內的 CSV / Parquet，依測站與 `config.yaml` 內所有 target 逐一訓練。單一模型失敗時會列印 skip 訊息並繼續處理其他組合。

## 推論介面

```python
from src.predict import predict
from src.preprocess import load_observations

df = load_observations("data/raw/高雄港.csv")
result = predict("高雄港", "wind_speed_gust", df, return_uncertainty=True)
```

回傳內容包含：

- `station_id`
- `target_group`
- `anchors`：H1-H4，每個錨點包含 offset、timestamp 與預測值。
- `accuracy_grade`：從最新評估報告讀取，供呼叫端判斷可信度。
- `model_version`
- `generated_at`

## 與前端整合

目前輸出的 anchors 可以轉成前端微氣候派工頁需要的欄位，例如：

- `wind_speed_gust` 對應平均風速與陣風。
- `precipitation` 對應雨量或雨量分級。
- `tide_level` 可作為港區作業輔助資訊。
- `accuracy_grade` 可對應前端顯示的模型可信度或風險提示。

前端目前仍使用 mock dispatch scenario。若要接入本模型，需要再做一層 API 或資料轉換，把 H1-H4 預測結果整理成前端的 `nowcast`、`cwa`、`ops`、`cards` 等結構。
