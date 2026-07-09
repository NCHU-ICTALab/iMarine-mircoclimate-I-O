# Port-local Data Acquisition v2.8 / v2.8.1

## CLI

```powershell
python kaohsiung_microclimate_lstm/src/tools/fetch_port_local_stations.py `
  --station-prefix KHWD `
  --output-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly
```

如果本機或 TWPort SSL 憑證檢查失敗，可暫時設定：

```powershell
$env:TWPORT_VERIFY_SSL='false'
```

## v2.8.1 Parser Patch

`src/data/twport_realtime_parser.py` 會解析 TWPort realtime panel 的 HTML/text 內容，支援：

```text
KHWD01
KHWD01M01
KHWD01M10
WS_AVG=3.336
WD_AVG=282
WS_MAX=6.53
WD_MAX=271
```

raw sensor id 會正規化為 canonical station id：

```text
KHWD01M01 -> KHWD01
KHWD01M10 -> KHWD01
```

## Reports

- `fetch_report.json`
- `quality_report.json`
- `station_availability_report.json`
- `normalization_report.json`

預設報表位置：

```text
kaohsiung_microclimate_lstm/results/port_local_data_v28/
```

## Current Status

目前已成功建立 6 個 KHWD CSV：

```text
KHWD01.csv
KHWD04.csv
KHWD05.csv
KHWD06.csv
KHWD07.csv
KHWD08.csv
```

因此 dispatch risk prediction mode 已從 `fallback_baseline` 切換為 `port_local_postprocess`。
