# v3.2 Rain Probability Training

v3.2 使用 nearby CWA/CODIS historical data 建立 rain event labels：

```text
target_rain_event_H1..H4 = future nearby_cwa_precipitation_1hr_max > 0.5 mm
target_heavy_rain_event_H1..H4 = future nearby_cwa_precipitation_1hr_max > 10 mm
```

## 模型

目前使用 `RandomForestClassifier` 作為 tree-based baseline。

## 實際成效

```text
H1 Brier Score: 0.0183
H1 AUC: 0.9638
H1 CSI: 0.5443
H1 FAR: 0.1810
H1 POD: 0.6187

H3 Brier Score: 0.0261
H3 AUC: 0.9274
H3 CSI: 0.3291
H3 FAR: 0.2536
H3 POD: 0.3705
```

## API 使用方式

當 nearby CWA historical model 通過驗收時，trace 會標示：

```json
{
  "rain_model_mode": "nearby_cwa_historical_rain_model_plus_cwa_prior",
  "rain_probability_preserved": true,
  "cwa_pop_used_as_model_input": false
}
```

CWA PoP 仍是 prior，不是模型 input。
