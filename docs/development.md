# 開發維護說明

## 主要目錄

```text
app/
  api.py                  FastAPI routes 與首頁儀表板
  contracts.py            穩定 v1 response builders
  config.py               環境設定
  models.py               正規化 observation dataclass
  storage.py              SQLite 儲存與新鮮度狀態
  forecast_engine.py      簡易趨勢預報
  collectors/
    twport.py             TWPort 即時 collector
    cwa.py                CWA 即時 collector
    cwa_historyapi.py     CWA historyapi collector
    cwa_marine_history.py CWA O-B0075-001 海象 collector
    cwa_history.py        CODiS fallback collector

tests/                    單元測試
docs/                     公開專案文件
```

## Contract 維護規則

穩定輸出合約位於：

```text
app/contracts.py
```

變更輸出時請遵守：

1. 不要重新命名或移除既有 `microclimate.v1` 欄位。
2. 不要改變既有 metrics 欄位的單位。
3. 非破壞性補充優先放在 `metadata`。
4. 若必須做破壞性變更，新增 schema version，不要直接改 v1 行為。
5. 同步更新 `tests/test_contracts.py`。

## Collector 維護規則

Collectors 應回傳 `TwPortObservation`，避免把來源專屬格式直接暴露到 v1 output。

允許放原始來源細節的位置：

- `TwPortObservation.raw_data`
- SQLite `raw_data`
- diagnostics endpoints

穩定 v1 output 不應包含：

- 完整 raw payload。
- API authorization keys。
- 來源臨時欄位名稱。

## 測試

執行測試：

```powershell
python -m pytest
```

執行語法編譯檢查：

```powershell
python -m compileall app tests
```

## Push 前檢查

確認私人或本地檔案沒有 staged：

```powershell
git status --short
```

不要提交：

- `.env`
- `*.sqlite3`
- 本地虛擬環境
- 私人規劃或規格文件
- 含 API key 的截圖或 logs

如果私人檔案已被 Git 追蹤：

```powershell
git rm --cached "<private-spec-file>"
git rm --cached "<private-prompt-file>"
```
