# 高雄港微氣候降雨模型改善 v2.1 摘要

日期：2026-07-07

## 已實作項目

- `src/model.py`
  - 新增 `focal_loss()`。
  - 新增 `precipitation_loss()`，使用 Focal Loss + rain-only MSE。
- `src/dataset.py`
  - 新增 `build_precipitation_sampler()`。
  - 雨量二元標籤改為可設定門檻，本次使用原始雨量 1.0 mm 對應的 scaled threshold。
- `src/train.py`
  - precipitation 訓練改用 Focal Loss。
  - precipitation 訓練集啟用 `WeightedRandomSampler`。
  - checkpoint 版本更新為 `baseline_lstm_v2.1`。
- `src/evaluate.py`
  - 新增 1 mm 與 10 mm 門檻的 CSI/FAR/POD/TP/FP/FN。
  - 修正 CSI 判級方向，CSI 現在為越高越好。
  - precipitation 評估會讀取 `inference_cls_threshold`。
- `src/predict.py`
  - precipitation 推論輸出新增 `rain_probability`、`heavy_rain_prob`、`data_source`。
- QPESUMS scaffold
  - 新增 `src/data/check_qpesums_availability.py`。
  - 新增 `src/data/fetch_qpesums.py`。
  - 新增 `src/data/qpesums_cache.py`。
  - 新增 `results/qpesums_availability.json`。

## 設定

本次實跑使用 `config_hourly_codis.yaml`：

- `focal_alpha: 0.85`
- `focal_gamma: 2.0`
- `lambda_reg: 0.5`
- `rain_threshold_main: 1.0`
- `rain_threshold_heavy: 10.0`
- `use_weighted_sampler: true`
- `inference_cls_threshold: 0.6`

## QPESUMS / QPE 可用性

候選資料集檢查結果：

- `O-A0002-001`：HTTP 200，`api_success=true`，1320 筆測站資料，可作為即時雨量 QPE fallback。
- `O-A0059-001`、`O-A0064-001`、`O-A0065-001`：目前回傳 404。

目前 `qpesums.enabled` 仍維持 `false`，因此正式訓練與推論預設為 `lstm_only`。若後續要讓前端或服務端使用即時 QPE，可再把 `qpesums.enabled` 改成 `true`。

## 467441 precipitation v2.1 實跑成效

- 權重：`models/checkpoints/467441_precipitation_best.pt`
- 評估：`results/evaluation/467441_precipitation_metrics.json`
- loss CSV：`logs/training/467441_precipitation_loss.csv`
- loss 圖：`results/plots/467441_precipitation_loss.png`
- 測試視窗：270

| Anchor | MAE | RMSE | CSI > 1mm | FAR > 1mm | CSI > 10mm | beats persistence | grade |
|---|---:|---:|---:|---:|---:|---|---|
| H1 | 1.568 mm | 5.792 mm | 0.093 | 0.773 | 0.000 | true | poor |
| H2 | 1.574 mm | 5.813 mm | 0.019 | 0.944 | 0.000 | true | poor |
| H3 | 1.674 mm | 5.874 mm | 0.060 | 0.833 | 0.000 | true | poor |
| H4 | 1.513 mm | 5.714 mm | 0.053 | 0.880 | 0.000 | true | poor |

## 結論

v2.1 修改後，降雨模型不再完全預測為無雨，CSI 從原本 0 提升到 H1 約 0.093，但仍未達規格目標 H1 > 0.30，且 FAR 偏高。這表示 class imbalance 已有改善，但 467441 hourly 資料對短延時降雨事件仍不足。

下一步若要繼續提升，優先順序應為：

1. 啟用並回填 QPE/QPF 類特徵，尤其是即時雨量或雷達估計雨量。
2. 針對 precipitation 另做 threshold sweep，輸出 precision/recall/CSI/FAR 最佳門檻。
3. 嘗試降低 learning rate 到 0.0002，或提高 `lambda_reg` 到 0.8，減少目前過擬合與雨量幅度低估。

## 驗證

- `python -m pytest tests/test_lstm_baseline_preprocess.py --basetemp .tmp_pytest_v21`
- 結果：2 passed
- precipitation 推論 smoke test：成功輸出 `rain_probability`、`heavy_rain_prob`、`data_source`
