# v3.0 Model Selection 與 Fallback Policy

## 選模順序

```text
port_local_model
port_local_postprocess
fallback_baseline
```

## port_local_model 採用條件

必須同時符合：

- dataset readiness 通過。
- port-local wind_speed / wind_gust model 已訓練。
- H1/H2 MAE 通過設定門檻。
- wind_speed H1 必須優於 persistence baseline。
- `critical_under_warning_count == 0`。

## fallback 到 port_local_postprocess

符合任一條件時 fallback：

- KHWD 歷史資料不足。
- dataset readiness 未通過。
- 模型尚未訓練。
- 模型 metrics 未通過驗收。
- critical under-warning 大於 0。

只要 KHWD 即時/CSV 資料仍可用，就使用 `port_local_postprocess`，且：

```json
{
  "fallback_to_467441": false,
  "467441_used_as_core_station": false
}
```

## fallback 到 467441 baseline

只有在 KHWD port-local 資料不可用、postprocess 也不可用時才使用：

```json
{
  "prediction_mode": "fallback_baseline",
  "fallback_to_467441": true,
  "467441_used_as_core_station": false
}
```

`467441_used_as_core_station` 必須維持 false，因為 467441 只代表 fallback baseline，不是高雄港港區核心測站。
