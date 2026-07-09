# 高雄港微氣候派工風險後端系統 v2.8 / v2.8.1

## 目的

v2.8 在 v2.7 的 port-local station priority 基礎上，新增港區本地資料抓取管線。v2.8.1 修正 TWPort 即時頁 parser，使系統可從頁面文字/HTML 中解析 `KHWDxxM01/M10` 類 raw sensor id，並正規化成 `KHWDxx`。

## 新增/修改模組

```text
src/data/twport_realtime_parser.py
src/data/port_local_twport_client.py
src/data/port_local_station_normalizer.py
src/data/port_local_station_quality.py
src/tools/fetch_port_local_stations.py
```

## API

```text
GET /api/v1/dispatch/risk?target_area=KHH&refresh_port_local=true
```

流程：

1. 讀取 `config/station_pool.yaml`
2. 找出 `KHWD/KHTD/KHAW` port-local stations
3. 從 TWPort 即時頁抓取 HTML/text
4. 使用 `twport_realtime_parser.py` 解析 KHWD realtime records
5. 正規化 canonical columns
6. 執行品質檢查
7. 寫入 `data/raw/observed_hourly/{station_id}.csv`
8. 執行 dispatch risk prediction

## v2.8.1 實際結果

目前已成功建立：

```text
KHWD01.csv
KHWD04.csv
KHWD05.csv
KHWD06.csv
KHWD07.csv
KHWD08.csv
```

目前 API 輸出：

- `model_version`: `kaohsiung_port_dispatch_risk_v2.8.1`
- `prediction_mode`: `port_local_postprocess`
- `using_port_local_station`: `true`
- `port_local_station_count`: `6`
- `fallback_to_467441`: `false`
- `467441_used_as_core_station`: `false`

## 測試

```powershell
python -m pytest tests/test_twport_realtime_parser.py tests/test_fetch_port_local_stations.py --basetemp .tmp_pytest_v281
```
