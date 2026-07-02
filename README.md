# 高雄港微氣候資料 API

這是一個以 Python/FastAPI 建立的微氣候資料服務，用來擷取、正規化並提供高雄港周邊的海氣象資料。此服務定位為後續排程、風險評估與其他模組的上游輸入來源。

這份公開 README 只說明可執行服務、操作方式與穩定 I/O 合約；私人規劃或規格文件不是執行專案必要內容，也不應提交到公開儲存庫。

## 功能

- TWPort 即時港區觀測資料。
- CWA 即時氣象觀測資料。
- CWA 歷史資料即時查詢，不將歷史回補寫入本地儲存。
- 透過 CWA `O-B0075-001` 查詢海象與潮位歷史資料。
- CODiS 備援歷史查詢，用於冷啟動或長時間停機後的補查。
- 首頁儀表板可查看資料新鮮度、過期/停擺狀態與手動抓取控制。
- `/api/v1/...` 提供版本化且穩定的 JSON 輸出合約。

## 快速開始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

編輯 `.env`，填入 CWA Open Data 授權碼：

```text
CWA_API_KEY=your-cwa-open-data-key
```

啟動 API：

```powershell
uvicorn app.api:app --reload
```

開啟首頁：

```text
http://127.0.0.1:8000/
```

Swagger 測試頁：

```text
http://127.0.0.1:8000/docs
```

## 設定

常用 `.env` 設定：

```text
CWA_API_KEY=
CWA_DATA_ID=O-A0001-001
CWA_STATION_NAMES=高雄,小港,旗后,高雄港
CWA_COUNTY_NAMES=高雄市
CWA_HISTORY_DATA_ID=O-A0001-001
CWA_HISTORY_STATIONS=467441:cwb:Kaohsiung
CWA_MARINE_DATA_ID=O-B0075-001
CWA_MARINE_STATION_IDS=C4P01,1786,COMC08,46714D,C4Q02,C4Q01
CWA_VERIFY_SSL=true
TWPORT_BASE_URL=https://wwtf.twport.com.tw/twport/display/Realtime_Panel_Port_GatData_2024.aspx
TWPORT_PORT_ID=5
TWPORT_VERIFY_SSL=true
DATABASE_URL=microclimate.sqlite3
```

如果本機 Python 環境遇到憑證鏈問題，可在受信任環境中暫時將對應的 verify 設為 `false`。

## I/O 總覽

### 輸入

服務接受三類輸入：

| 輸入類型 | 位置 | 用途 |
| --- | --- | --- |
| 執行設定 | `.env` | API key、來源 ID、測站篩選、資料庫路徑 |
| 手動抓取請求 | Admin endpoints 與首頁按鈕 | 觸發 TWPort/CWA 即時資料抓取 |
| 歷史資料即時查詢 | `/api/v1/cwa/history` | 查詢 CWA 歷史資料，不寫入 SQLite |

外部資料來源：

| 來源 | 資料 | 本地儲存 |
| --- | --- | --- |
| TWPort | 即時風、能見度、潮位、浪、海流 | 執行 admin fetch 時寫入 |
| CWA Open Data | 即時氣象觀測 | 執行 admin fetch 時寫入 |
| CWA historyapi | 陸上氣象歷史資料 | 不寫入 |
| CWA `O-B0075-001` | 滾動 48 小時海象/潮位資料 | 不寫入 |
| CODiS fallback | 備援測站歷史資料 | 不寫入 |

### 中間儲存

即時抓取資料會寫入 SQLite：

```text
microclimate.sqlite3
```

主要資料表：

```text
microclimate_observations
```

CWA 歷史回補查詢刻意採即時查詢，不寫入 SQLite，避免本地儲存持續成長。

### 輸出

後續模組應優先使用穩定 v1 endpoints：

```text
GET /api/v1/schema
GET /api/v1/microclimate/current
GET /api/v1/microclimate/forecast?minutes=90
GET /api/v1/cwa/history?hours=24&source=official_land
```

舊版 endpoints，例如 `/microclimate/current`，仍保留給相容與人工檢查；新模組不應依賴其輸出格式。

## 穩定輸出合約

所有 v1 endpoints 使用相同 response envelope：

```json
{
  "schema_version": "microclimate.v1",
  "endpoint": "/api/v1/microclimate/current",
  "generated_at": "2026-07-02T18:45:00+08:00",
  "time_zone": "Asia/Taipei",
  "request": {},
  "metadata": {},
  "data_quality": {},
  "data": []
}
```

`data` 內每筆 observation 使用固定 record shape：

```json
{
  "record_id": "twport:WIND:KHWD01M01:observed:2026-07-02T18:40:00+08:00",
  "source": "twport",
  "device_type": "WIND",
  "station": {
    "station_id": "KHWD01M01",
    "station_name": "station display name",
    "location": "station location",
    "port_code": "5",
    "longitude": 120.28,
    "latitude": 22.61,
    "elevation": null
  },
  "time": {
    "observed_at": "2026-07-02T18:40:00+08:00",
    "fetched_at": "2026-07-02T18:43:00+08:00",
    "time_zone": "Asia/Taipei"
  },
  "metrics": {
    "wind_speed_mps": 2.5,
    "wind_gust_mps": 4.1,
    "wind_direction_deg": 270.0,
    "wind_gust_direction_deg": null,
    "precipitation_10min_mm": null,
    "precipitation_1hr_mm": null,
    "precipitation_24hr_mm": null,
    "air_temperature_c": null,
    "relative_humidity_percent": null,
    "air_pressure_hpa": null,
    "visibility_m": null,
    "tide_level": null,
    "tide_level_unit": "raw",
    "wave_height_m": null,
    "wave_period_s": null,
    "wave_max_height_m": null,
    "current_speed_mps": null,
    "current_direction_deg": null
  },
  "quality": {
    "is_forecast": false,
    "confidence": "high",
    "stale_at_fetch": false,
    "status_level": "current",
    "status_label": "正常",
    "is_stale_now": false,
    "obs_age_minutes": 5,
    "fetch_age_minutes": 2,
    "threshold_minutes": 20,
    "expected_update_interval": "現場風站約 1-5 分鐘；模擬風站可能整點更新"
  }
}
```

相容性規則：

- `schema_version` 維持 `microclimate.v1` 時，既有欄位名稱與單位不可變更。
- 破壞性變更必須新增版本，例如 `microclimate.v2`。
- v1 輸出不暴露來源原始 payload。

完整合約可查：

```text
GET /api/v1/schema
```

## 主要 Endpoints

### 首頁與健康檢查

```text
GET /
GET /health
GET /docs
```

### 手動抓取

```text
POST /admin/fetch?wind_mode=1
POST /admin/fetch-cwa
POST /admin/fetch-all?wind_mode=1
```

`wind_mode` 支援：

| 值 | 意義 |
| --- | --- |
| `1` | 1 分鐘平均風速 |
| `10` | 10 分鐘平均風速 |
| `15` | 15 分鐘平均風速 |

### 穩定 v1 輸出

```text
GET /api/v1/schema
GET /api/v1/microclimate/current
GET /api/v1/microclimate/forecast?minutes=90
GET /api/v1/cwa/history?hours=24&source=official_land
```

`/api/v1/cwa/history` 支援：

| 參數 | 可用值 |
| --- | --- |
| `hours` | `6`, `12`, `24`, `48` |
| `source` | `official_land`, `marine`, `all`, `codis_fallback` |

### 診斷

```text
GET /microclimate/status
GET /cwa/history/diagnostics?hours=6
```

`/microclimate/status` 適合檢查資料新鮮度。`/cwa/history/diagnostics` 會檢查 CWA 歷史與海象來源是否可用，並遮蔽 CWA key。

## 文件

更細的操作與規則文件：

- [I/O 合約](docs/io_contract.md)
- [資料來源與新鮮度規則](docs/data_sources.md)
- [操作手冊](docs/operations.md)
- [開發維護說明](docs/development.md)

## 測試

```powershell
python -m pytest
```

目前測試涵蓋 parser 行為、CWA 正規化、歷史資料 collectors、儲存層新鮮度狀態、預報輸出與 v1 contract shape。

## 安全與公開儲存庫注意事項

- 不要提交 `.env`。
- 不要提交本地 SQLite 資料庫。
- 不要提交私人規劃或規格文件。
- 不要把 API key 放進 logs、README 範例、截圖或 issue。
- 如果私人檔案已被 Git 追蹤，push 前先從 index 移除：

```powershell
git rm --cached "<private-spec-file>"
git rm --cached "<private-prompt-file>"
```

## 已知限制

- TWPort parser 依賴目前 HTML table 結構。
- CWA 歷史查詢為即時查詢，刻意不落地儲存。
- 短期預報是簡易趨勢估計，不是精準天氣預報。
