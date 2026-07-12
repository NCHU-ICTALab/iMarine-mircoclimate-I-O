# 高雄港微氣候預測系統

本專案實作高雄港微氣候與派工風險（dispatch risk）預測系統。目前的實作依據是
`高雄港微氣候預測_專案規格書_v1.3.md`（工作文件，未納入git版控，見文末說明）；
較早的 v2.0 章節內容則保留作為實作歷史紀錄。

## 系統目標

- 預測未來 30、60、90、120 分鐘（H1~H4）的短期微氣候錨點。
- 依據風速、陣風、降雨機率／雨量、潮位、能見度提供派工風險決策依據。
- 有港區在地觀測資料時優先使用，並讓「退回備援資料」的行為明確可追溯。
- 資料品質、模型選用、測站使用狀況、系統稽核結果都要能被檢視（inspectable），不是黑盒。

## 系統架構

實作依循 v1.3 / v2.0 的分層架構：

1. **資料蒐集**：台灣港務公司（TWPort）、中央氣象署（CWA）開放資料、CWA海象觀測、
   CODiS歷史雨量、潮位／波浪觀測。
2. **資料前處理與品質控制**：測站資料正規化、過期資料檢查、歷史資料集就緒性檢查、
   缺值處理。
3. **特徵工程**：時序滑動窗、測站優先序特徵、港區風速聚合、鄰近CWA測站聚合、
   降雨機率先驗值。
4. **模型訓練與評估**：LSTM基準模型、港區在地樹模型、鄰近CWA歷史模型、模型註冊表
   （model registry）、評估指標。
5. **預測與派工風險**：決定性模型選用、後處理（post-processing）、風險等級對應、
   行動等級對應。
6. **API與報表**：FastAPI端點、儀表板資料負載、系統稽核報表、CLI工具。

## 環境安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r kaohsiung_microclimate_lstm\requirements.txt
Copy-Item .env.example .env
```

**兩個 requirements 檔案都要裝**：`requirements.txt` 是FastAPI伺服器本身需要的套件；
`kaohsiung_microclimate_lstm\requirements.txt` 是建模／預測管線需要的套件（pandas、
scikit-learn、torch、pyarrow等）。只裝第一個的話伺服器仍能啟動，但因為這些
import是延遲載入（lazy import），所有跟派工風險有關的端點（`/api/v1/dispatch/risk`、
`/dispatch-risk-demo` 等）會在實際呼叫時才報錯，不會在啟動時就發現。

若 PowerShell 執行 `Activate.ps1` 出現「未經數位簽署」或執行原則（execution policy）
相關錯誤，可先用系統管理員權限的 PowerShell 執行一次：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 環境變數（`.env`）

`.env.example` 複製過去之後，一般本地開發不需要改任何東西就能跑。比較常用到的欄位：

```text
CWA_API_KEY=                 # 中央氣象署開放資料API金鑰（選填，見下方說明）
DATABASE_URL=microclimate.sqlite3
FETCH_ON_STARTUP=false       # 是否在伺服器啟動時立刻抓一次資料
ALERT_WIND_SPEED=13.8        # 風速警戒閾值（m/s）
ALERT_WIND_GUST=17.2         # 陣風警戒閾值（m/s）
```

若要串接前端，記得把 `CORS_ALLOWED_ORIGINS` 改成前端實際的網域（逗號分隔多個網域）；
本地開發預設是 `*`（不限制）。

CWA開放資料金鑰（選填，沒有的話部分CWA相關端點會回傳「不可用」而非報錯）：

```text
CWA_API_KEY=你自己申請的CWA開放資料金鑰
```

**切記不要把真實的API金鑰commit進git。**

## 啟動demo（最常見的使用情境）

**第一步：啟動後端伺服器**，在專案根目錄開一個終端機執行：

```powershell
uvicorn app.api:app --reload --host 127.0.0.1 --port 8010
```

- `--reload` 是開發模式，程式碼存檔後會自動套用；正式環境或長時間跑建議拿掉
  `--reload`，改成手動重啟（每次改完程式碼要重新執行這行指令才會生效）。
- 如果直接指定Python執行檔路徑（例如系統上裝了多個Python版本），PowerShell要用
  `&`（call operator）開頭才能執行帶引號的路徑，例如：

  ```powershell
  & "C:\Path\To\python.exe" -m uvicorn app.api:app --host 127.0.0.1 --port 8010
  ```

  直接貼一個帶引號的路徑字串（不加`&`）在PowerShell裡不會被當成指令執行，會出現
  「運算式或陳述式中有未預期的語彙基元」之類的解析錯誤。

- 看到終端機顯示 `Uvicorn running on http://127.0.0.1:8010` 就是啟動成功，這個
  視窗要保持開著。

**第二步：瀏覽器打開demo頁面**

```text
http://127.0.0.1:8010/dispatch-risk-demo
```

demo頁面可以輸入目標區域、勾選「模擬KHWD不可用」等測試情境、按「抓取最新資料」
手動刷新所有CWA／港區即時資料快取。

**關閉伺服器**：終端機視窗按 `Ctrl+C`。若是背景執行、找不到視窗，可用
`netstat -ano | findstr :8010` 找出佔用該連接埠的PID，再用
`Stop-Process -Id <PID> -Force` 結束。

## 主要API端點

```text
GET  /                                          首頁
GET  /dispatch-risk-demo                        互動式demo頁面
GET  /health                                    健康檢查
GET  /docs                                      Swagger自動文件
GET  /api/v1/schema                             API schema總覽

GET  /api/v1/system/info                        系統資訊
GET  /api/v1/system/requirements                需求規格
GET  /api/v1/system/data-spec                   資料規格
GET  /api/v1/system/feature-spec                特徵規格
GET  /api/v1/system/model-spec                  模型規格
GET  /api/v1/system/evaluation-spec             評估規格
GET  /api/v1/system/api-spec                    API規格
GET  /api/v1/system/deployment-spec             部署規格
GET  /api/v1/system/testing-spec                測試規格
GET  /api/v1/system/schedule-spec               排程規格
GET  /api/v1/system/appendix-spec               附錄規格

GET  /api/v1/microclimate/current               目前微氣候觀測值
GET  /api/v1/microclimate/forecast?minutes=90    未來N分鐘預測（可搭配extended windows）

GET  /api/v1/dispatch/risk?target_area=KHH       派工風險預測（主要端點，H1~H4完整結果）
GET  /api/v1/dispatch/model-status?target_area=KHH   目前各anchor使用的模型狀態
GET  /api/v1/dispatch/station-usage?target_area=KHH  各測站資料使用狀況
GET  /api/v1/dispatch/system-audit?target_area=KHH   系統稽核報表（模型可用性、資料完整性）

GET  /cwa/history?source=...                    CWA歷史預報比對資料
GET  /cwa/history/diagnostics                    CWA歷史資料累積診斷

POST /admin/fetch                                依 wind_mode 手動抓取（單一來源）
POST /admin/fetch-cwa                            手動刷新CWA預報來源
POST /admin/fetch-all                            手動刷新全部來源（含模式參數）
POST /admin/fetch-microclimate-sources           demo頁「抓取最新資料」按鈕實際呼叫的端點
GET  /admin/scheduler-status                     自動排程目前啟用/停用狀態
```

`/api/v1/dispatch/risk` 是最重要的端點，回傳每個時間錨點（H1~H4）的風速、陣風、
降雨機率、雨量、能見度預測，以及每個數值背後用了哪個模型、哪些後處理機制
（可從回傳內容的 `source_detail`／`trace` 欄位查到）。

## 資料刷新機制

demo頁面的「抓取最新資料」按鈕會呼叫 `POST /admin/fetch-microclimate-sources`，
一次執行以下所有任務：

- KHWD／KHTD／KHAW 港區在地觀測
- O-B0075-001 海象即時觀測
- 六個鄰近CWA測站（C0V*）即時觀測
- CWA降雨機率預報來源（用於H1~H4混合）
- CWA +3h／+6h延伸預報卡片快取
- CWA預報歷史紀錄（供日後回測比對用）

自動排程機制已經接好，但預設是關閉的（避免多耗背景資源）。要開啟的話，編輯
`kaohsiung_microclimate_lstm/config.yaml`：

```yaml
auto_fetch_scheduler:
  enabled: true
```

改完要重啟API服務才會生效。預設間隔：港區在地觀測10分鐘、海象即時觀測240分鐘、
鄰近CWA即時觀測15分鐘、CWA預報歷史180分鐘。可用 `GET /admin/scheduler-status`
查看目前排程狀態。

## 專案結構

```text
app/                            FastAPI應用程式、資料收集器、儲存層、API contract
kaohsiung_microclimate_lstm/    建模、訓練、預測、風險評估、系統稽核管線
tests/                          主要測試套件
docs/                           API contract、維運筆記、實作稽核紀錄
```

`kaohsiung_microclimate_lstm/data/raw/historical_weather/`（訓練用原始歷史資料）與
`kaohsiung_microclimate_lstm/data/processed/`（訓練管線中間產物）**不納入git版控**，
因為體積大且可以從公開資料來源重新產生。`kaohsiung_microclimate_lstm/models/` 底下
已訓練好的模型檔案則有納入版控，所以拉下repo後不用重新訓練就能直接跑API。資料來源、
如何在本機重新產生訓練資料、原始資料如何變成訓練好的模型，詳見
[`docs/dataset_guide.md`](docs/dataset_guide.md)。

## CLI工具

v2.0 CLI包裝可用以下方式呼叫：

```powershell
python -m kaohsiung_microclimate_lstm.src.cli --help
```

範例：

```powershell
python -m kaohsiung_microclimate_lstm.src.cli evaluate --station-id 467441 --target wind_speed_gust --config kaohsiung_microclimate_lstm/config.yaml

python -m kaohsiung_microclimate_lstm.src.cli system-audit --target-area KHH --config kaohsiung_microclimate_lstm/config.yaml
```

v1.3 資料與基準測試工具：

```powershell
python -m kaohsiung_microclimate_lstm.src.data.fetch_marine_history --output-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly

python -m kaohsiung_microclimate_lstm.src.tools.run_model_benchmark --dataset path/to/training.csv --target wind_speed --output-dir kaohsiung_microclimate_lstm/results/model_benchmark_v13
```

## 驗證（跑測試）

執行主要測試套件：

```powershell
python -m pytest
```

根目錄的 `pytest.ini` 刻意把預設測試範圍限定在 `tests/` 底下。

修改任何跟預測邏輯、後處理、API contract有關的程式碼後，建議至少做到：

1. `python -m pytest` 全部通過（無回歸）。
2. 實際啟動uvicorn，用瀏覽器或curl打對應端點，確認回傳內容符合預期
   （測試套件涵蓋不到所有實際執行情境，尤其是並發、快取、真實外部資料的行為）。

## 規格書檔案

現行v1.3規格書與較早的v2.0規格書都放在repo根目錄，但排除在git版控之外
（`.gitignore` 裡的 `*規格書*.md`），因為這些是協調各輪實作用的工作文件，
不是要交付的專案產出：

```text
高雄港微氣候預測_專案規格書_v1.3.md
高雄港微氣候預測系統_v2.0_規格書_前半部.md
高雄港微氣候預測系統_v2.0_規格書_後半部.md
```

每一輪實作完成的項目會整理進：

```text
docs/spec_v13_implementation_summary.md
```
