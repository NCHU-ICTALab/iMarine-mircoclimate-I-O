# v3.2 Model Selection Fallback Policy

## Fallback Chain

```text
port_local_model
port_local_postprocess
nearby_cwa_historical_model
fallback_baseline
```

## 原則

- `port_local_model`：只有 KHWD 歷史資料足夠且模型通過驗收才使用。
- `port_local_postprocess`：KHWD 即時資料可用時優先使用。
- `nearby_cwa_historical_model`：KHWD 即時資料不可用時，作為比 467441 更靠近港區的歷史模型 fallback。
- `fallback_baseline`：最後才使用 467441 baseline。

## 467441 限制

`467441` 永遠不是高雄港港區核心測站：

```json
{
  "467441_used_as_core_station": false
}
```

## 目前實際選模

目前 KHWD 即時資料可用，且 nearby CWA historical model 已訓練並通過驗收，因此實際選模為：

```json
{
  "selected_mode": "port_local_postprocess",
  "nearby_cwa_historical_model_accepted": true,
  "fallback_to_nearby_cwa_historical_model": false,
  "fallback_to_467441": false
}
```
