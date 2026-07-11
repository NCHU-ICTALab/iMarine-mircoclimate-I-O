# 高雄港微氣候預測 v1.3 實作摘要

更新時間：2026-07-11 10:00（Asia/Taipei）

## 本次新增

- 已依規格書第 12.1 節新增 `POST /admin/fetch-microclimate-sources`，統一觸發四個資料抓取來源：港區 KHWD/KHTD/KHAW、O-B0075-001 商港海象即時資料、Nearby CWA 六站即時資料、CWA 預報發布紀錄。
- 已在 `dispatch-risk-demo` 工具列新增「抓取最新資料」按鈕，按下後會停用按鈕、呼叫後端抓取端點，完成後重新整理派工風險預測。
- 已新增 `app/fetch_microclimate.py`，讓手動按鈕與未來排程共用同一組抓取流程，避免重複實作。
- 已新增 `app/scheduler.py`，支援 `auto_fetch_scheduler.enabled` 控制是否啟用背景排程；預設關閉，關閉時不建立 APScheduler 背景執行緒。
- 已新增 `GET /admin/scheduler-status`，可檢查排程是否啟用、各 job 的設定間隔與下次執行時間。
- 已在 `kaohsiung_microclimate_lstm/config.yaml` 加入預設排程設定：港區 10 分鐘、海象 240 分鐘、Nearby CWA 15 分鐘、CWA 預報紀錄 180 分鐘。
- 已更新 `README.md`，補上手動抓取端點、排程狀態端點與「如何開啟自動排程」說明。

## 既有 v1.3 成果

- 降雨量 mm 來源已改接 `nearby_cwa_live` 六站，不再誤用 KHWD 港區風速資料。
- 降雨量輸出已採條件式流程：降雨機率未達門檻時輸出 0mm，達門檻才使用 H1~H4 雨量回歸模型。
- 派工輸出已新增 H1-H3 三小時累積估計，並明確標註這是 H1~H3 預測值加總，不是真正觀測累積。
- 已新增並訓練增水殘差模型腳本 `kaohsiung_microclimate_lstm/src/tools/train_surge_residual_model.py`。
- 已維持 `port_local_postprocess` 作為派工風險預設模式，KHWD 即時安全門檻覆寫仍保留為保守決策。

## 驗證結果

- 本次完整測試：`197 passed`
- 已新增測試覆蓋：
  - `/admin/fetch-microclimate-sources` 會呼叫共用抓取 runner。
  - `/admin/scheduler-status` 預設回報排程關閉。
  - `auto_fetch_scheduler.enabled: false` 時不建立背景排程器。
  - `auto_fetch_scheduler.enabled: true` 時會註冊四個 interval jobs。
  - `dispatch-risk-demo` HTML 內含「抓取最新資料」按鈕與手動抓取端點。

## 注意事項

- 手動抓取與排程只使用 O-B0075-001 即時海象資料；O-B0075-002 30 天歷史回填維持 CLI 手動執行，不會在按鈕或常態排程中觸發。
- FastAPI `@app.on_event` 目前可正常運作，但測試會出現 deprecation warning；後續若整理 API 啟動流程，可改成 lifespan 寫法。
