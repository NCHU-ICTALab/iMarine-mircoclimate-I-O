# 高雄港微氣候派工風險後端系統 v2.9

## 目的

v2.9 在 v2.8.1 已能取得 KHWD 港區風站資料的基礎上，新增 port-local wind/gust 後處理驗證，並明確保留 rain probability 輸出。

## 新增模組

```text
src/data/port_local_wind_aggregation.py
src/postprocess/port_local_wind_postprocess.py
src/postprocess/port_local_gust_postprocess.py
```

## 流程

```text
KHWD CSV
  -> port-local wind/gust aggregation
  -> wind/gust postprocess validation for H1/H2

rain probability model
  -> nearby / port-local rain postprocess if available
  -> CWA PoP prior for H3/H4
  -> final rain probability

final rain + postprocessed wind + postprocessed gust
  -> dispatch risk
  -> risk trigger
  -> dispatch action
```

## 實際結果

- `model_version`: `kaohsiung_port_dispatch_risk_v2.9`
- `prediction_mode`: `port_local_postprocess`
- `port_local_wind_station_count`: `6`
- `fallback_to_467441`: `false`
- `467441_used_as_core_station`: `false`
- `rain_probability_preserved`: `true`

目前 KHWD 最大風速/陣風未超過 warning threshold，因此 v2.9 驗證 report 顯示 H1/H2 wind/gust postprocess checked but not applied。

## Reports

```text
results/dispatch_risk_v29/port_local_postprocess_report.json
results/dispatch_risk_v29/rain_probability_report.json
results/dispatch_risk_v29/dispatch_risk_trace_report.json
```
