# 資料來源與新鮮度規則

本服務會將多個外部來源正規化成同一個內部觀測模型，並透過穩定 v1 輸出合約提供給後續模組。

## 來源角色

| 來源 | 角色 | 儲存方式 |
| --- | --- | --- |
| TWPort | 主要港區現場微氣候觀測 | 抓取時寫入 |
| CWA Open Data | 補充雨量、溫度、濕度、氣壓與風 | 抓取時寫入 |
| CWA historyapi | 陸上氣象歷史資料即時查詢 | 不寫入 |
| CWA `O-B0075-001` | 海象、潮位、浮標與海流歷史資料即時查詢 | 不寫入 |
| CODiS fallback | 冷啟動或來源中斷時的備援歷史資料 | 不寫入 |

## TWPort 風速時間尺度

手動 TWPort 抓取支援：

| `wind_mode` | 意義 |
| --- | --- |
| `1` | 1 分鐘平均風速 |
| `10` | 10 分鐘平均風速 |
| `15` | 15 分鐘平均風速 |

## CWA 歷史資料模式

`GET /api/v1/cwa/history` 支援：

| `source` | 說明 |
| --- | --- |
| `official_land` | CWA historyapi 陸上氣象觀測 |
| `marine` | CWA `O-B0075-001` 滾動 48 小時海象/潮位資料 |
| `all` | 合併 `official_land` 與 `marine` |
| `codis_fallback` | 備援用途，通常到上一個完整日 |

支援的 `hours`：

```text
6, 12, 24, 48
```

## 預設海象站點

預設海象站點以高雄港與鄰近海域參考為主：

| Station ID | 名稱 | 角色 |
| --- | --- | --- |
| `C4P01` | 高雄潮位站 | 主要港區潮位 |
| `1786` | 永安潮位站 | 北側鄰近潮位 |
| `COMC08` | 彌陀資料浮標 | 北側鄰近浮標 |
| `46714D` | 小琉球資料浮標 | 南側鄰近浮標 |
| `C4Q02` | 東港潮位站 | 南側鄰近潮位 |
| `C4Q01` | 小琉球潮位站 | 南側鄰近潮位 |

可透過 `.env` 覆寫：

```text
CWA_MARINE_STATION_IDS=C4P01,1786,COMC08,46714D,C4Q02,C4Q01
```

## 新鮮度規則

資料狀態會在回應時即時計算。Collector 寫入時的 `stale` 欄位不是唯一判斷依據。

| 來源 | 資料類型 | 預期更新 | 過期門檻 |
| --- | --- | --- | --- |
| TWPort | `WIND` | 現場站約 1-5 分鐘；部分模擬站可能整點更新 | 20 分鐘 |
| TWPort | `VISIBILITY` | 約 1-5 分鐘 | 20 分鐘 |
| TWPort | `TIDE` | 視來源列而定，數分鐘到每小時 | 75 分鐘 |
| TWPort | `WAVE` | 多為每小時 | 75 分鐘 |
| TWPort | `CURRENT` | 多為每小時 | 75 分鐘 |
| TWPort | `AWAC` | 約 30-60 分鐘 | 90 分鐘 |
| TWPort | `STABILITY` | 多為每小時 | 75 分鐘 |
| CWA | `WEATHER` | 約每小時 | 75 分鐘 |

若某測站最新觀測時間超過 24 小時，會標示為 `outage`。

## 診斷

使用：

```text
GET /cwa/history/diagnostics?hours=6
```

診斷 endpoint 會回傳：

- CWA historyapi metadata 檔案數。
- CWA data-id list endpoint 是否回空物件。
- 目前選用的海象測站 ID、名稱、最新觀測時間與資料列數。
- CODiS fallback 角色與測站設定。

診斷回應會遮蔽 CWA authorization key。
