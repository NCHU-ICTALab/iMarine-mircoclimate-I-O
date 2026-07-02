# 操作手冊

## 啟動服務

```powershell
uvicorn app.api:app --reload
```

開啟：

```text
http://127.0.0.1:8000/
```

## 首頁操作流程

1. 開啟首頁儀表板。
2. 選擇 TWPort 風速時間尺度：`1`、`10` 或 `15` 分鐘。
3. 按 `更新全部` 抓取 TWPort 與 CWA 即時觀測。
4. 檢查摘要卡與表格中是否有過期或停擺資料。
5. 使用 `最新資料 JSON` 查看穩定 v1 current output。

## 手動抓取 Endpoints

```text
POST /admin/fetch?wind_mode=1
POST /admin/fetch-cwa
POST /admin/fetch-all?wind_mode=1
```

一般手動刷新建議使用 `POST /admin/fetch-all`。

## CWA 歷史查詢

首頁可選：

- 時間窗：`6`、`12`、`24`、`48` 小時。
- 來源：
  - `陸上氣象`：CWA historyapi。
  - `海象潮位`：CWA `O-B0075-001`。
  - `官方全部`：陸上氣象與海象潮位合併。
  - `CODiS 備援`：只作備援。

穩定 API：

```text
GET /api/v1/cwa/history?hours=24&source=official_land
GET /api/v1/cwa/history?hours=24&source=marine
GET /api/v1/cwa/history?hours=24&source=all
GET /api/v1/cwa/history?hours=24&source=codis_fallback
```

歷史查詢結果不會寫入 SQLite。

## 診斷

```text
GET /health
GET /microclimate/status
GET /cwa/history/diagnostics?hours=6
GET /api/v1/schema
```

使用 `/microclimate/status` 檢查目前資料新鮮度。使用 `/api/v1/schema` 確認後續模組使用的輸出合約。

## 常見問題

### CWA Key 未設定

如果 `CWA_API_KEY` 是空的，CWA 即時與歷史資料呼叫都不會有有效資料。

### SSL 憑證錯誤

部分本機 Python 環境可能會對外部來源發生憑證驗證錯誤。在受信任網路中可設定：

```text
CWA_VERIFY_SSL=false
TWPORT_VERIFY_SSL=false
```

正式或接近正式環境建議盡量維持憑證驗證開啟。

### 部分資料看起來過期

不同來源更新頻率不同。可先查：

```text
GET /microclimate/status
```

查看 `status_level`：

- `current`：可用。
- `stale`：偏舊，建議降權或忽略。
- `outage`：該測站來源疑似長時間停擺。

### 終端機中文亂碼

PowerShell 可能因 console 設定而錯誤顯示 UTF-8 JSON。瀏覽器與一般 JSON client 應會正常收到 UTF-8。

## 建議執行模式

本機或手動使用：

1. 啟動服務。
2. 觸發 `POST /admin/fetch-all?wind_mode=1`。
3. 讀取 `/api/v1/microclimate/current`。
4. 只有在模組需要歷史資料時才查 `/api/v1/cwa/history`。

自動化使用：

- TWPort 約每 5 分鐘抓一次。
- CWA 即時資料約每 10 分鐘抓一次。
- CWA 歷史資料維持 on-demand，避免本地儲存成長。
