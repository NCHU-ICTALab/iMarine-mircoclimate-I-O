# CWA Rain Fetcher (中央氣象署降雨資訊監控系統)

本專案是一個輕量、美觀且獨立的微氣候子專案，專門用於抓取、儲存與視覺化呈現中央氣象署 (CWA) 的**降雨機率預報 (F-C0032-001)** 與 **自動雨量觀測站實測數據 (O-A0002-001)**。

---

## 🌟 主要功能
1. **氣象局 API 串接**：支援非同步 (`httpx`) 抓取 CWA 開放資料平台之 JSON 預報與觀測數據。
2. **SQLite 本地時序存儲**：將抓取到的降雨數據存入 SQLite 資料庫中，具備重複鍵值更新 (upsert) 機制，確保觀測與預報資料不重複。
3. **極致美觀的 Dashboard**：使用 Vanilla CSS 與現代的玻璃擬態 (Glassmorphism) 暗色調風格，提供響應式介面，支援：
   - 即時同步按鈕（點擊直接向氣象局獲取最新資料）。
   - 縣市 36 小時降雨機率折線圖（整合 Chart.js）。
   - 最新雨量觀測站實測數據排序（支援按縣市篩選）。
   - 顯示最新同步狀態與全台今日雨量最大站點。

---

## 🛠 專案目錄結構
```text
cwa_rain_fetcher/
  ├── app/
  │    ├── __init__.py
  │    ├── config.py         # 環境變數載入與路徑設定
  │    ├── cwa_client.py     # CWA API 請求與 JSON 解析
  │    ├── storage.py        # SQLite 資料表建立、Upsert 與查詢邏輯
  │    └── api.py            # FastAPI Web 端點與 Dashboard 渲染
  ├── tests/
  │    ├── __init__.py
  │    └── test_fetcher.py   # 單元與整合測試
  ├── .env                   # 本地設定檔 (API Key, Port)
  ├── .env.example
  ├── run.py                 # Uvicorn 啟動腳本
  ├── requirements.txt
  └── README.md
```

---

## 🚀 快速開始

### 1. 安裝套件
請於虛擬環境中安裝必要依賴：
```bash
pip install -r requirements.txt
```

### 2. 設定環境變數
於 `cwa_rain_fetcher/.env` 內填入您的 CWA API 授權碼：
```env
CWA_API_KEY=your-cwa-api-key
PORT=8010
```

### 3. 啟動 Web 服務
執行啟動指令：
```bash
python run.py
```
啟動後，開啟瀏覽器造訪：[**http://127.0.0.1:8010**](http://127.0.0.1:8010)

---

## 🧪 執行測試
使用 pytest 執行專案測試：
```bash
python -m pytest tests/
```
