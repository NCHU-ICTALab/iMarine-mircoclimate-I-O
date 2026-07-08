# 高雄港微氣候降雨模型整合 v2.2 摘要

日期：2026-07-07

## 已實作項目

- 新增 `src/data/fetch_rain_spatial.py`
  - 使用 CWA `O-A0002-001` 即時雨量站資料。
  - 以高雄港附近座標選取 30 km 內最近 3 站。
  - 輸出 `nearby_precip_1/2/3` 與 `nearby_available`。
- 新增 `src/data/fetch_cwa_forecast.py`
  - 支援 CWA `F-D0047-065` 3 小時降雨機率 PoP3h。
  - 輸出 `cwa_pop_current`、`cwa_pop_next`、`cwa_data_age_hr`、`cwa_available`。
- 新增 `src/tune/threshold_sweep.py`
  - 掃描 precipitation inference threshold。
  - 輸出 `results/threshold_sweep_467441_precipitation.csv`。
  - 輸出 `results/plots/threshold_sweep_467441_precipitation.png`。
- 修改 `src/preprocess.py`
  - 訓練資料沒有即時 spatial/CWA 特徵時，依規格補 0 與 availability mask。
  - precipitation 支援 target 專屬 `lookback_hours: 24`。
- 修改 `src/predict.py`
  - 推論時會注入附近雨量站與 CWA PoP3h 特徵。
  - precipitation 輸出新增 `data_sources`、`spatial_available`、`cwa_available`。
- 修改 `src/evaluate.py`
  - 降雨評級門檻改為 v2.2 目標。
- 修改 `config*.yaml`
  - 新增 `features.spatial_rain` 與 `features.cwa_forecast`。
  - precipitation 設定改為 `lookback_hours: 24`、`focal_alpha: 0.75`、`lambda_reg: 0.8`。

## API 實測狀態

### Spatial rain

`O-A0002-001` 可用，已選取最近 3 個雨量站：

| station_id | name | distance |
|---|---|---:|
| C0V690 | 鼓山 | 1.40 km |
| C0V490 | 新興 | 1.49 km |
| CAP070 | 高雄燈塔 | 2.43 km |

目前即時 1 小時雨量皆為 0.0 mm。

### CWA PoP3h

`F-D0047-065` 目前未成功取得 `鼓山區` PoP3h，推論 fallback 為：

- `cwa_pop_current: 0.0`
- `cwa_pop_next: 0.0`
- `cwa_data_age_hr: 6.0`
- `cwa_available: false`

## v2.2 訓練設定

- 模型版本：`baseline_lstm_v2.2`
- 權重：`models/checkpoints/467441_precipitation_best.pt`
- lookback：24 hours
- features：19 個
- threshold main：1.0 mm
- threshold heavy：10.0 mm
- Focal Loss：`alpha=0.75`、`gamma=2.0`
- rain-only MSE：`lambda_reg=0.8`
- sampler：WeightedRandomSampler

特徵欄位：

`wind_speed`, `wind_gust`, `precipitation_1hr`, `nearby_precip_1`, `nearby_precip_2`, `nearby_precip_3`, `nearby_available`, `cwa_pop_current`, `cwa_pop_next`, `cwa_data_age_hr`, `cwa_available`, `wind_dir_sin`, `wind_dir_cos`, `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`, `tide_sin`, `tide_cos`

## Threshold Sweep

- 最佳 threshold：0.35
- mean CSI：0.1756
- mean FAR：0.8047
- 注意：沒有任何掃描門檻能達到 FAR < 0.55，因此選擇的是 CSI 最高的門檻。

## 467441 precipitation v2.2 成效

測試視窗：645

| Anchor | MAE | RMSE | CSI > 1mm | FAR > 1mm | CSI > 10mm | beats persistence | grade |
|---|---:|---:|---:|---:|---:|---|---|
| H1 | 3.911 mm | 6.504 mm | 0.108 | 0.882 | 0.000 | false | poor |
| H2 | 3.397 mm | 6.216 mm | 0.114 | 0.872 | 0.000 | false | poor |
| H3 | 2.706 mm | 5.443 mm | 0.204 | 0.788 | 0.000 | false | poor |
| H4 | 1.389 mm | 4.780 mm | 0.277 | 0.677 | 0.000 | true | poor |

## 推論 Smoke Test

成功輸出：

- `model_version: baseline_lstm_v2.2`
- `data_sources.spatial_rain.available: true`
- `data_sources.cwa_forecast.available: false`
- anchor 內含 `rain_probability`、`heavy_rain_prob`、`data_source`、`spatial_available`、`cwa_available`

範例 H1：

- `rain_probability: 0.568`
- `precipitation_1hr: 1.95 mm`
- `data_source: spatial_rain+lstm`

## 結論

v2.2 已完成整合流程與推論資料格式，但成效仍不建議作為派工排程核心條件。

主要原因：

- 訓練歷史資料中 spatial/CWA 特徵只能補 0/mask，模型無法真正學到這些即時外部特徵與未來降雨的歷史關係。
- threshold sweep 後 CSI 有提升，尤其 H3/H4，但 FAR 仍過高。
- H1/H2 的 MAE 變差，且未打敗 persistence。
- 強降雨 CSI 仍為 0。

目前可用定位：

- 前端可以顯示 `rain_probability` 與附近雨量站狀態。
- 可作為「低信心降雨提醒」。
- 不應作為自動派工、停工或改期的主要依據。

## 驗證

- `python -m pytest tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v22`
- 結果：2 passed
