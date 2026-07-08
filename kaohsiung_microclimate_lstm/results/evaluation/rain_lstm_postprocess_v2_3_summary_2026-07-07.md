# 高雄港微氣候降雨後處理 v2.3 摘要

日期：2026-07-07

## 核心修正

PDF 規格指出 v2.2 的主要問題是 train-inference mismatch：

- 訓練時：`nearby_precip_*` 與 `cwa_*` 皆為 0。
- 推論時：同欄位填入即時真值。
- 結果：LSTM 推論看到訓練期間未出現過的輸入分布，造成 H1 MAE 明顯惡化。

本次已改為：

- LSTM 只吃純時序特徵。
- nearby precipitation 與 CWA PoP3h 不再進入 LSTM。
- 外部資料只用於 LSTM 輸出後的 probability postprocess。

## 已新增模組

- `src/postprocess/rain_probability_rules.py`
  - Rule 1：附近單站 1hr 雨量 > 0.5 mm，H1/H2 機率至少 0.70。
  - Rule 2：附近平均 1hr 雨量 > 2.0 mm，H1/H2 機率至少 0.85。
  - Rule 3：CWA current PoP > 0.60，H1-H4 機率至少 `PoP * 0.8`。
  - Rule 4：CWA current PoP < 0.10 且附近無雨，H1/H2 最高壓到 0.15。
  - warning level：normal/watch/warning/stop。
- `src/forecast/rain_probability_blender.py`
  - H1/H2 不混 CWA。
  - H3 = 0.5 * rule_adjusted + 0.5 * CWA current。
  - H4 = 0.3 * rule_adjusted + 0.7 * CWA next。
- `src/cwa/pop3h_client.py`
  - 取得 CWA `F-D0047-065` PoP3h，輸出 current/next。
- `src/cwa/location_resolver.py`
  - 自動測試候選行政區，輸出 `config/resolved_cwa_location.json`。
- `src/tools/resolve_cwa_location.py`
  - CLI 版本 location resolver。
- `src/predict.py`
  - 新增 `predict_rain_probability_v23()`。

## 訓練結果

已重新訓練 467441 precipitation：

- checkpoint：`models/checkpoints/467441_precipitation_best.pt`
- model version：`baseline_lstm_v2.3_pure_temporal`
- feature count：11
- forbidden feature check：通過，無 `nearby_*`、`cwa_*`、`qpe_*`

目前 LSTM 特徵：

`wind_speed`, `wind_gust`, `precipitation_1hr`, `wind_dir_sin`, `wind_dir_cos`, `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`, `tide_sin`, `tide_cos`

## 評估結果

此表為純時序 LSTM base model 的歷史測試集評估；即時 postprocess 依賴目前 nearby/CWA observations，無法直接用同一份歷史資料完整回測。

| Anchor | MAE | RMSE | CSI > 1mm | FAR > 1mm | CSI > 10mm | beats persistence | grade |
|---|---:|---:|---:|---:|---:|---|---|
| H1 | 1.632 mm | 5.189 mm | 0.110 | 0.835 | 0.000 | false | poor |
| H2 | 1.717 mm | 5.250 mm | 0.075 | 0.884 | 0.000 | false | poor |
| H3 | 1.409 mm | 5.067 mm | 0.148 | 0.733 | 0.000 | false | poor |
| H4 | 1.378 mm | 5.025 mm | 0.058 | 0.893 | 0.000 | true | poor |

## CWA Location Resolver

已測試候選：

- 前鎮區
- 鼓山區
- 苓雅區
- 三民區
- 鹽埕區
- 小港區

目前 CWA `F-D0047-065` 對這些候選皆回 0 records，因此 resolved fallback 為 `前鎮區`，推論時會自動 fallback 到 LSTM + nearby postprocess。

## 推論 Smoke Test

輸出格式已符合 v2.3：

- `model_version: rain_lstm_postprocess_v2.3`
- `base_model_version: baseline_lstm_v2.3_pure_temporal`
- anchors 含：
  - `raw_lstm_probability`
  - `rule_adjusted_probability`
  - `final_probability`
  - `warning_level`
  - `cwa_blending_applied`
  - `applied_rules`
- `trace.train_inference_mismatch_fixed: true`
- `trace.pure_temporal_lstm: true`

本次即時狀態：

- nearby rain available：true
- nearby max 1hr：0.0 mm
- CWA PoP3h available：false
- 因沒有附近降雨且 CWA 不可用，postprocess 未觸發規則，final probability 等於 raw LSTM probability。

## 測試

- `tests/test_rain_probability_rules.py`
- `tests/test_rain_probability_blender.py`
- `tests/test_lstm_baseline_preprocess.py`

結果：7 passed

## 結論

v2.3 已修正 v2.2 的架構錯誤，避免再把推論時才有的外部特徵餵進 LSTM。
目前降雨仍不建議作為派工排程核心依據，但 v2.3 的輸出比較適合前端展示風險：

- H1/H2：純 LSTM + nearby rain postprocess。
- H3/H4：若 CWA 可用，加入 PoP3h blending。
- 每個 anchor 都有 warning level，可作為低信心雨量警示。
