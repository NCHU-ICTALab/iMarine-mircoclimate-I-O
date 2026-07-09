# 高雄港微氣候派工風險後端系統 v2.7

## 目的

v2.7 修正高雄港派工風險模型的測站語意：預測目標是高雄港區域 `KHH`，不是 CWA `467441` 單一測站。`467441` 只能在港區本地測站不可用時作為 fallback/baseline。

## 資料優先序

1. `KHWDxx`: 高雄港本地風站，核心風速/陣風來源。
2. `KHTDxx`: 高雄港本地潮位站，reference only。
3. `KHAWxx`: 高雄港波浪/流場資料，reference only。
4. CWA 前鎮區 PoP3h，後處理 prior。
5. `467441`: fallback baseline。
6. `C4Q01`, `C4Q02`, `C4P01`, `COMC08`: reference only。

## Prediction Mode

- `port_local_model`: 已有經驗證的港區本地模型且 KHWD 資料充足。
- `port_local_postprocess`: KHWD 資料充足，但尚未完成港區模型重訓，因此用既有 baseline 加港區後處理。
- `fallback_baseline`: 港區本地資料不足或不可用，回退到 `467441` baseline。

目前本機資料沒有 `KHWD/KHTD/KHAW` 觀測檔，因此實際模式為 `fallback_baseline`。

## 新增/修改模組

```text
src/data/station_metadata_validator.py
src/data/station_priority.py
src/data/multi_station_loader.py
src/predict.py
config/station_pool.yaml
```

## API

主要呼叫：

```text
GET /api/v1/dispatch/risk?target_area=KHH
```

舊版相容：

```text
GET /api/v1/dispatch/risk?target_station_id=467441
```

舊版呼叫不會讓 `467441` 變成核心測站，僅會在 trace 中標示 legacy/fallback proxy。

## 實際 v2.7 結果

輸出位置：

```text
results/dispatch_risk_v27/prediction_samples.json
results/dispatch_risk_v27/metrics.json
results/dispatch_risk_v27/cwa_fetch_report.json
results/dispatch_risk_v27/reliability_report.json
results/evaluation/dispatch_risk_v2_7_port_local_priority_summary_2026-07-08.md
```

目前結果：

- `prediction_mode`: `fallback_baseline`
- `using_port_local_station`: `false`
- `fallback_to_467441`: `true`
- `467441_used_as_core_station`: `false`
- H1: `watch`, action `observe_only`
- H2-H4: `normal`, action `normal_dispatch`

## 測試

```powershell
python -m pytest tests/test_station_priority.py tests/test_station_metadata_validator.py tests/test_prediction_mode_decision.py tests/test_predict_dispatch_risk_v27.py tests/test_dispatch_risk_api_v27.py --basetemp .tmp_pytest_v27
```
