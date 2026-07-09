# v3.0 Port-local Model Training

## Dataset Builder

CLI：

```powershell
python kaohsiung_microclimate_lstm/src/tools/build_port_local_training_dataset.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --input-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly `
  --output kaohsiung_microclimate_lstm/data/processed/port_local_training_dataset.parquet `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v30
```

主要特徵：

```text
khwd_wind_speed_mean/max/min/std
khwd_wind_gust_mean/max/min/std
khwd_station_count
khwd_valid_wind_station_count
khwd_valid_gust_station_count
khwd_wind_direction_sin_mean/cos_mean
khwd_gust_direction_sin_mean/cos_mean
hour_sin/hour_cos
doy_sin/doy_cos
lag1/lag2
roll3
```

標籤：

```text
target_wind_speed_H1..H4
target_wind_gust_H1..H4
```

## Readiness

預設門檻：

```text
min_total_samples: 500
min_valid_label_samples_per_horizon: 100
min_training_days: 14
max_feature_missing_ratio: 0.30
max_label_missing_ratio: 0.30
```

目前實際 KHWD 資料尚未達標，因此訓練流程會跳過模型訓練並輸出失敗原因。

## Training

CLI：

```powershell
python kaohsiung_microclimate_lstm/src/tools/train_port_local_model.py `
  --config kaohsiung_microclimate_lstm/config.yaml `
  --dataset kaohsiung_microclimate_lstm/data/processed/port_local_training_dataset.parquet `
  --output-dir kaohsiung_microclimate_lstm/models/port_local_v30 `
  --report-dir kaohsiung_microclimate_lstm/results/dispatch_risk_v30
```

資料達標時會訓練 RandomForest baseline：

```text
port_local_wind_speed_model: H1-H4
port_local_wind_gust_model: H1-H4
```

雨量機率模型只有在 port-local rain labels 可用時才會延伸；目前維持 existing rain model + CWA prior。
