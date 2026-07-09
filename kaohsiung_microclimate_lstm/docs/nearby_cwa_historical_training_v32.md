# v3.2 Nearby CWA Historical Training

## 資料來源

v3.2 使用 `Raingel/historical_weather` downloader 取得 CWA/CODIS 逐時歷史資料，欄位正規化後輸出到：

```text
data/processed/nearby_cwa_historical/{station_id}.parquet
```

## 實際 backfill 結果

本次抓取區間：

```text
2023-01-01 到 2026-07-08
```

成功測站：

```text
C0V890, C0V490, C0V810, C0V840, C0V450, C0V900, C0V680, C0V610
```

每站資料筆數：`30,769`

## Ranking 結果

以高雄港 reference points 計算最短距離後，選出比 `467441` 更靠近港區的 6 站：

```text
C0V890, C0V490, C0V840, C0V810, C0V450, C0V900
```

`467441` 距離港區 reference points 約 `12.9715 km`，上述 6 站皆更近。

## Readiness

```json
{
  "ready": true,
  "station_count": 6,
  "sample_count": 184614,
  "training_days": 1282,
  "valid_wind_samples": 184385,
  "valid_gust_samples": 183821,
  "valid_rain_samples": 184614
}
```

## Model Metrics

nearby CWA historical model 已訓練完成，並通過 v3.2 驗收門檻。

重點指標：

```text
wind_speed H1 MAE: 0.5919 m/s
wind_speed H2 MAE: 0.5920 m/s
wind_gust H1 MAE: 0.6835 m/s
wind_gust H2 MAE: 0.6835 m/s
rain H1 Brier Score: 0.0183
rain H1 AUC: 0.9638
critical_under_warning_count: 0
```

## 使用限制

nearby CWA historical model 是 fallback historical model，不是 KHWD port-local core model。當 KHWD 即時資料可用時，API 仍優先使用 `port_local_postprocess`。
