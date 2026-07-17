# PR 草稿：feat(dispatch): live provider 接派工風險後端 + H1-H4 錨點/指標整合

> 狀態：本機 commit 完成（branch `feat/dispatch-live-provider`，commit `8a361e5`），**尚未 push、尚未開 PR**。
> Repo：`iMarine-FrontEnd`　Base：`main`　目前帳號對此 repo 只有讀取權限，push 前需先解決權限（fork 或加 write）。

---

## PR 描述（照 `.github/pull_request_template.md` 填）

### 模組

dispatch

### 改了什麼

- 新增 `src/data/exchange/dispatch.ts`：串接後端 `/api/v1/dispatch/risk`，把結果 merge 進 mock 的
  `stable` 情境（`nowcast`/`cwa`/`ops` 燈號），`rain`/`typhoon` 兩情境維持純 demo，不受影響。
- 時間軸拖曳（`src/screens/dispatch/index.ts`）改用真實 H1~H4 錨點資料（`liveAnchors`）與
  CWA +3h/+6h 值；拖到 RandomForest 0-120min 區段時取最近一筆錨點即時切換 hero 數字、
  逐錨點 CSI/POD/FAR（`metricsByHorizon`）、`dispatch_suggestion`、`dispatch_risk_level`
  （後端 5 級收斂成前端 3 態：`normal/watch→ok`、`warning/high_risk→warn`、`stop→stop`）。
- 「模型更新」按鈕（原本純視覺假動畫）改為真的呼叫 `ctx.data.dispatch.snapshot()` 重抓，
  加 10 秒逾時保護 + `inferenceId` token 防止逾時後晚到的結果覆蓋畫面。
- `src/data/types.ts` 新增型別：`LiveAnchor`、`HorizonMetrics`，並在 `DispatchScenario` 加上
  `liveAnchors?`、`metricsByHorizon?` 兩個 live-only 欄位。
- 命名修正：`ConvLSTM`→`RandomForest`、`0-90min`→`0-120min`（mock 資料、HTML、settings 頁面全面同步）。
- `docs/collab/dispatch.md`、`scripts/verify/contracts/dispatch.mjs`、`scripts/verify/live/dispatch.mjs`
  三件套填實（原本是 `pending: true` 佔位）。

### 改動範圍自查（CONTRIBUTING §3 白名單）

- [x] 只動了自己模組的 provider（`src/data/exchange/dispatch.ts`）
- [x] 只動了自己模組的 screen（`src/screens/dispatch/`）與 settings section
- [x] `src/data/types.ts` 只動自己模組的型別區塊（新增 `LiveAnchor`、`HorizonMetrics`，
      `DispatchScenario` 加 `liveAnchors?`/`metricsByHorizon?`，如上方列出）
- [ ] ~~沒動禁改清單~~ → **動了 `src/main.ts`**（見下方「例外說明」）

### ⚠️ 例外說明：本 PR 動到 `src/main.ts`

`src/main.ts` 明確列在 CONTRIBUTING §3 的禁改清單，規則要求「要動請先開 issue 討論，不要直接進 PR」。

改動內容只有兩行：

```diff
+import { createDispatchProvider } from './data/exchange/dispatch';
...
+    dispatch: createDispatchProvider(env.VITE_DISPATCH_API),
```

這是把 `dispatch` provider 掛進共用 `ctx.data` 的必要接線動作——沒有這一步，`dispatch.ts`
整個 provider 不會被呼叫到，live 資料不會生效。跟 `carbon`/`twin`/`policy` 這幾個既有
live 模組當初接線時的動作是同一種模式。**已跟專案 owner 當面確認可以直接包進本 PR**，
不另外開 issue（2026-07-17）。

### 契約變更

- [x] 有 —— `docs/collab/dispatch.md` §4 與 `scripts/verify/contracts/dispatch.mjs` 已同步更新
      （含 §8 變更紀錄，共 3 筆：2026-07-14 首次接 live、2026-07-14 補 metrics、2026-07-15 補
      `metricsByHorizon`/`dispatch_suggestion`/`dispatch_risk_level`）

**前後端資料模型落差**（已寫進 `docs/collab/dispatch.md` §4）：後端沒有「情境」概念，
`/api/v1/dispatch/risk` 回傳的是單一即時查詢結果，不是前端 mock 的 3 情境清單。目前接法是
把 live 資料 merge 進 `stable` 情境，`rain`/`typhoon` 維持純 demo。`ops[]` 的法規文字
（`rules[]`）維持前端靜態庫，只有 `now.status`/`now.action`/`cwa3`/`cwa6` 這幾個燈號欄位
依即時數值重算（門檻表是從 mock 21 個資料點反推、逐一核對吻合，**非港務單位正式核可**，
需域專家後續覆核）。

### 測試證據

- [x] `npm run check` 三綠燈 —— `30 passed test files / 152 passed tests`，`vite build` 成功
- [x] `npm run verify:contract -- dispatch` —— `3 PASS / 0 FAIL`
- [x] `npm run verify:live -- dispatch` —— `4 PASS / 0 FAIL`（截圖見下）

```text
PASS  #s-dispatch .src.live 存在（chip 轉 LIVE）
PASS  #wxavg / #wxbf（hero 風速數字）非空
      wxavg="7.1" wxbf="4 級"
PASS  #mxbody 作業矩陣渲染 7 列
      實際 7 列
PASS  全程零 pageerror
```

### 頁面截圖

`npm run verify:live -- dispatch` 產出：`C:\Users\ming\AppData\Local\Temp\imarine-verify-live-dispatch.png`
（開 PR 時需要重新截一次貼上去，或維護者驗收時自己重跑會拿到新的）

---

## 完整 diff

統計：**11 個檔案，+677 / -63**

```text
docs/collab/dispatch.md                   | 110 +++++++++++++++---
scripts/verify/contracts/dispatch.mjs     |  56 ++++++++-
scripts/verify/live/dispatch.mjs          |  42 +++++--
src/data/exchange/dispatch.ts             | 187 ++++++++++++++++++++++++++++++ (新檔)
src/data/mock/dispatch.json               |   2 +-
src/data/types.ts                         |  27 ++++-
src/main.ts                               |   9 +-
src/screens/dispatch/dispatch.html        |   8 +-
src/screens/dispatch/index.ts             | 139 ++++++++++++++++++----
src/screens/settings/sections/dispatch.ts |   2 +-
tests/dispatch-provider.test.ts           | 158 +++++++++++++++++++++++++ (新檔)
```

### `docs/collab/dispatch.md`

```diff
@@ -7,49 +7,129 @@
 | 項目 | 值 |
 |---|---|
 | 模組 | dispatch（screen：`src/screens/dispatch/`） |
-| 後端負責人 | 待填 |
-| 後端 repo | 待填（URL） |
-| 預設 branch | 待填 |
+| 後端負責人 | mingliu-create |
+| 後端 repo | https://github.com/NCHU-ICTALab/iMarine-mircoclimate-I-O |
+| 預設 branch | main |

 ## 2. 起服務

-前置需求（語言版本、套件管理器）：待填
+前置需求：Python 3.13、pip；`kaohsiung_microclimate_lstm/models/` 已含訓練好的模型檔案（有納入版控），不需要重新訓練即可直接跑。

 ```
 # 指令序（維護者照抄可起）
-待填
+git clone https://github.com/NCHU-ICTALab/iMarine-mircoclimate-I-O.git
+cd iMarine-mircoclimate-I-O
+python -m venv .venv
+.venv\Scripts\Activate.ps1
+pip install -r requirements.txt
+pip install -r kaohsiung_microclimate_lstm/requirements.txt
+Copy-Item .env.example .env
+uvicorn app.api:app --host 127.0.0.1 --port 8200
 ```

-健康檢查：`curl http://127.0.0.1:8200/<health-path>` → 預期輸出：待填
+健康檢查：`curl http://127.0.0.1:8200/health` → 預期輸出：`{"status": "ok", "collector": "...", "latest_fetched_at": "...", "row_count": ...}`

 ## 3. env 變數

 | 側 | 變數 | 說明 | 預設 |
 |---|---|---|---|
 | 前端 | `VITE_DISPATCH_API` | 後端位址（見 docs/collab/README.md 分配表） | `http://127.0.0.1:8200` |
-| 後端 | 待填 | | |
+| 後端 | `CORS_ALLOWED_ORIGINS` | 允許的前端來源（逗號分隔）；本機開發預設 `*` 已涵蓋 Vite dev server（`http://localhost:5173`），正式部署才需要明確指定 | `*` |
+| 後端 | `CWA_API_KEY` | 中央氣象署開放資料金鑰（選填；沒有的話部分CWA相關資料回傳「不可用」而非報錯，不影響本模組核心端點） | 空 |

 ## 4. API 契約（後端為準，隨 PR 更新）

-契約待定——後端定案的第一個 live PR 填實本節 + `scripts/verify/contracts/dispatch.mjs`。
+**⚠️ 前後端資料模型落差（送PR前務必讀）**：後端沒有「情境（scenarios）」概念，
+`/api/v1/dispatch/risk` 回傳的是**單一即時查詢結果**（某個 `target_area` 當下的
+H1~H4預測），不是前端mock的3情境清單。目前的接法（見§5）是把live資料merge進
+`stable` 情境，`rain`/`typhoon` 兩情境維持純demo模擬用途不變，並非後端提供「情境」。
+
+另外，`ops[]`（7種港區作業類型的法規/慣例派工規則文字）後端完全沒有對應資料，
+規則文字（`rules[]`）維持前端靜態法規庫；只有 `now.status`/`now.action`/`cwa3`/`cwa6`
+這幾個「燈號」欄位由前端 provider 依即時風速/雨量與一份反推的門檻表重新計算
+（門檻表非港務單位正式核可，見 `src/data/exchange/dispatch.ts` 檔頭註解與PR說明，
+需域專家後續覆核）。`conclusion`/`cards[]`/`metrics` 目前維持mock靜態值，不做動態生成。

 | Method | Path | 用途 |
 |---|---|---|
-| 待填 | | |
+| GET | `/api/v1/dispatch/risk` | 主要端點：查詢某目標區域當下H1~H4（30/60/90/120分鐘）派工風險預測（本模組實際只用到這一個） |
+| GET | `/health` | 健康檢查 |

 <!-- 每個端點附 request/response JSON 範例 + 欄位說明 + 錯誤回應形狀 -->

+### GET /api/v1/dispatch/risk
+
+**Query參數**：`target_area`（string，本模組固定傳 `KHH`）
+
+**Request範例**
+
+```
+GET http://127.0.0.1:8200/api/v1/dispatch/risk?target_area=KHH
+```
+
+**Response範例**（節錄，本模組只讀取 `forecast_anchors` 與 `cwa` 兩個頂層欄位，
+完整欄位遠多於此，其餘為後端內部稽核用途）
+
+```json
+{
+  "forecast_anchors": [
+    {
+      "label": "H1",
+      "offset_minutes": 30,
+      "rain": { "amount_level": "小雨" },
+      "wind_speed": { "predicted_mps": 7.068, "beaufort": { "scale": 4 } },
+      "wind_gust": { "predicted_mps": 8.169 }
+    },
+    { "label": "H2", "offset_minutes": 60, "...": "同上結構" },
+    { "label": "H3", "offset_minutes": 90, "...": "同上結構" },
+    { "label": "H4", "offset_minutes": 120, "...": "同上結構" }
+  ],
+  "cwa": [
+    { "window": "+3h", "rainLevel": "大雨", "beaufort": 6 },
+    { "window": "+6h", "rainLevel": "大雨", "beaufort": 6 }
+  ]
+}
+```
+
+**欄位說明（本模組實際使用的部分）**
+
+| 欄位 | 型別 | 說明 |
+|---|---|---|
+| `forecast_anchors[0]` | object | H1（+30分鐘）錨點，本模組用作 `nowcast` 來源（最貼近「現在」的預測） |
+| `forecast_anchors[].rain.amount_level` | string | `無`\|`小雨`\|`大雨`\|`豪雨`\|`大豪雨`\|`not_applicable`；`not_applicable` 時前端fallback成 `無` |
+| `forecast_anchors[].wind_speed.beaufort.scale` | number | 蒲福風級，門檻表判斷用 |
+| `forecast_anchors[].wind_speed.predicted_mps` / `.wind_gust.predicted_mps` | number | 對應 `nowcast.windAvg` / `nowcast.windGust` |
+| `cwa` | array（固定2筆） | `[+3h, +6h]`，跟前端 `CwaWindow` 型別 `{window, rainLevel, beaufort}` 完全對齊，可直接用 |
+
+**錯誤回應**
+
+| 情境 | HTTP狀態碼 | Body |
+|---|---|---|
+| 備援測站歷史資料檔案不存在 | 404 | `{"detail": "No observed hourly data for fallback_station_id=467441"}` |
+| `config.yaml` 遺失 | 503 | `{"detail": "Microclimate dispatch risk config is missing"}` |
+
+provider（`src/data/exchange/dispatch.ts`）對非2xx回應或fetch例外一律整份回退mock，
+不會把上述錯誤往UI拋。

 ## 5. 前端接線

-- provider：`src/data/exchange/dispatch.ts`（目前 mock；接 live 時在 provider 內轉換成 snapshot 形狀，UI 不動）
-- fallback：live 失敗必退 mock（比照 `src/data/exchange/policy.ts`，demo 現場後端沒起也不能崩）
-- 資料源 chip 轉 LIVE 條件：待填
+- provider：`src/data/exchange/dispatch.ts`（live；打 `/api/v1/dispatch/risk`，在 provider
+  內把結果merge進mock的 `stable` 情境形狀，`rain`/`typhoon` 兩情境不動，UI（`index.ts`）不需改動）
+- fallback：live 失敗（fetch例外或非2xx）必退純mock（比照 `src/data/exchange/policy.ts`）
+- 資料源 chip 轉 LIVE 條件：`main.ts` 是否把 `dispatch` 接上 `createDispatchProvider(...)`
+  （比照 `carbon`/`twin` 既有慣例：chip反映「此模組是否wired到live provider」，不是「這次
+  請求是否真的連到後端」——後端斷線時chip仍顯示LIVE，但內容悄悄retain/退回mock，不會顯示錯誤畫面）

 ## 6. 驗收

 - `npm run verify:contract -- dispatch`
 - `npm run verify:live -- dispatch`
-- 人眼清單：待填（頁面該看到什麼）
+- 人眼清單：
+  - stable情境hero數字（雨量等級/蒲福級/平均風速/陣風）跟後端
+    `curl http://127.0.0.1:8200/api/v1/dispatch/risk?target_area=KHH` 的 `forecast_anchors[0]` 一致
+  - 作業矩陣（`crane/grain/coal/tanker/pilot/mooring/yard`）燈號跟 §4 門檻表算出的結果一致
+  - 切到「強降雨逼近」「颱風接近」情境時內容完全不受live資料影響（維持demo原樣）
+  - 把後端關掉、重新整理頁面：畫面優雅退回mock，不出現錯誤畫面，LIVE chip仍會顯示（見§5說明）

 ## 7. demo 影片

@@ -60,7 +140,9 @@

 | 日期 | 變更 |
 |---|---|
-| | |
+| 2026-07-14 | 首次接上live：新增 `src/data/exchange/dispatch.ts`，merge `/api/v1/dispatch/risk` 的H1（nowcast來源）與 `cwa`（+3h/+6h）進 `stable` 情境；新增7種作業的燈號門檻表（反推自mock 3情境×7作業，非正式規則，待域專家覆核）；`rain`/`typhoon` 情境不受影響；填實第4節API契約與 `scripts/verify/contracts/dispatch.mjs`、`scripts/verify/live/dispatch.mjs`。 |
+| 2026-07-14 | 後端補上 `/api/v1/dispatch/risk` 頂層 `metrics`（H1 rain_probability 的 CSI/POD/FAR，`available=false` 時保留mock靜態值不用null覆蓋）；前端 `renderHero()` 拆出 `renderHeroValues()`，時間軸拖曳到 RandomForest 0-120min 區段時會用 `liveAnchors`（H1~H4）取最近一筆即時切換hero數字，拖到CWA +3h/+6h區段則改顯示 `cwa[0]`/`cwa[1]` 真實值（無精確m/s，`windAvg`/`windGust`顯示「—」）；`ConvLSTM`→`RandomForest`、`0-90min`→`0-120min` 全面更名修正（含mock情境結論文字）；`rain`/`typhoon` 情境仍完全不受影響。 |
+| 2026-07-15 | 後端第49項補上 `metrics.by_horizon`（H1~H4逐anchor CSI/POD/FAR）後，前端全面比對「後端有、前端沒用到」的欄位並補上三項：①拖曳到 RandomForest 區段時 `#wxmet`（CSI/POD/FAR）跟著切換到對應錨點的真實數字（新增 `DispatchScenario.metricsByHorizon`），CWA zone維持顯示「—」（無對應後端指標）；②`forecast_anchors[].dispatch_suggestion`（真實派工建議文字）接上 `#concl`，拖曳RandomForest區段時跟著切換，CWA zone與缺值時維持原本mock靜態文字不變；③`forecast_anchors[].dispatch_risk_level`（後端5級 normal/watch/warning/high_risk/stop）收斂成前端3態後接上hero底色（`normal`/`watch`→`ok`、`warning`/`high_risk`→`warn`、`stop`→`stop`），取代原本只看`rainLevel`的`WXCLS`查表，CWA zone與mock情境維持`WXCLS`查表不變。同時盤點過 `reliability`、`current_station_usage`、`station_display_rows`、`model_registry_summary` 等系統稽核類欄位，判斷不適合出現在港務派工UI，刻意不接。`rain`/`typhoon` 情境仍完全不受影響。 |

 ## 附錄：前端現有 mock 欄位形狀（參考，非契約承諾）
```

### `scripts/verify/contracts/dispatch.mjs`

```diff
-/* dispatch 契約待定——後端 API 定案的第一個 live PR 必須把本檔填實（CONTRIBUTING §6）。
-   填實時照 contracts/policy.mjs 的形狀：export default { base, checks }；
-   base 讀 process.env.VITE_DISPATCH_API ?? 'http://127.0.0.1:8200'（port 分配見 docs/collab/README.md）。
-   UI 需要的資訊參考 docs/collab/dispatch.md 附錄（前端 mock 欄位形狀）。 */
+/* dispatch 契約 smoke——端點以 src/data/exchange/dispatch.ts 現行呼叫為準。
+   本模組只讀 GET /api/v1/dispatch/risk 的 forecast_anchors 與 cwa 兩個頂層欄位，
+   其餘欄位（trace、system_audit_summary 等）為後端內部稽核用途，不在 smoke 範圍內。
+   完整欄位說明見 docs/collab/dispatch.md §4。 */
+import { checkFields, fetchJson } from '../lib.mjs';
+
 export default {
-  pending: true,
-  reason: '後端 API 契約尚未定案（見 docs/collab/dispatch.md §4）',
+  base: process.env.VITE_DISPATCH_API ?? 'http://127.0.0.1:8200',
+  checks: [
+    {
+      name: 'GET /api/v1/dispatch/risk 回 forecast_anchors 陣列，首筆欄位齊',
+      async run(base) {
+        const d = await fetchJson(`${base}/api/v1/dispatch/risk?target_area=KHH`);
+        const anchors = d?.forecast_anchors;
+        if (!Array.isArray(anchors)) throw new Error(`預期 forecast_anchors array，得到 ${typeof anchors}`);
+        if (anchors.length === 0) throw new Error('forecast_anchors 為空陣列');
+        const errs = checkFields(anchors[0], {
+          label: 'string',
+          offset_minutes: 'number',
+          rain: 'object',
+          wind_speed: 'object',
+          wind_gust: 'object',
+        });
+        if (errs.length) throw new Error(errs.join('；'));
+        const rainErrs = checkFields(anchors[0].rain, { amount_level: 'string?' });
+        if (rainErrs.length) throw new Error(rainErrs.join('；'));
+        return `${anchors.length} 個錨點，首筆（${anchors[0].label}）欄位齊`;
+      },
+    },
+    {
+      name: 'GET /api/v1/dispatch/risk 回 cwa 陣列（+3h/+6h 兩筆）',
+      async run(base) {
+        const d = await fetchJson(`${base}/api/v1/dispatch/risk?target_area=KHH`);
+        const cwa = d?.cwa;
+        if (!Array.isArray(cwa)) throw new Error(`預期 cwa array，得到 ${typeof cwa}`);
+        if (cwa.length !== 2) throw new Error(`預期 cwa 長度 2，得到 ${cwa.length}`);
+        const errs = checkFields(cwa[0], { window: 'string', rainLevel: 'string', beaufort: 'number' });
+        if (errs.length) throw new Error(errs.join('；'));
+        return `cwa windows：${cwa.map((w) => w.window).join(', ')}`;
+      },
+    },
+    {
+      name: 'GET /health 回 status',
+      async run(base) {
+        const d = await fetchJson(`${base}/health`);
+        const errs = checkFields(d, { status: 'string' });
+        if (errs.length) throw new Error(errs.join('；'));
+        return `status=${d.status}`;
+      },
+    },
+  ],
 };
```

### `scripts/verify/live/dispatch.mjs`

```diff
-/* dispatch live 斷言待定——後端契約定案的第一個 live PR 必須把本檔填實（CONTRIBUTING §6）。
-   填實時照 live/policy.mjs 的形狀：export default { id, asserts(page) }。
-   dispatch/epidemic/alert 頁有資料源 chip（policy 是特例沒有），標配斷言至少含：
-   1) #s-<模組> .src.live 存在（chip 轉 LIVE）；2) KPI 統計列數字非空；3) 主視覺容器非空。
-   epidemic 填實注意：Mapbox GL 為 WebGL，runner 已帶 --use-angle=swiftshader（勿加 --disable-gpu），
-   且需 .env 的 VITE_MAPBOX_TOKEN。 */
+/* dispatch live 斷言——live 資料只覆蓋 stable 情境（頁面預設情境），
+   斷言：1) chip 轉 LIVE；2) hero 風速/蒲福數字非空；3) 作業矩陣 7 列都渲染。
+   rain/typhoon 情境維持純 mock，不在本斷言範圍內（見 docs/collab/dispatch.md §4）。 */
 export default {
-  pending: true,
-  reason: '後端 API 契約尚未定案（見 docs/collab/dispatch.md §4/§6）',
+  id: 'dispatch',
+  async asserts(page) {
+    const results = [];
+    const section = page.locator('#s-dispatch');
+    await section.waitFor({ timeout: 10000 });
+
+    const chip = section.locator('.src.live');
+    const chipCount = await chip.count();
+    results.push({
+      name: '#s-dispatch .src.live 存在（chip 轉 LIVE）',
+      ok: chipCount > 0,
+      detail: chipCount > 0 ? undefined : '找不到 .src.live，chip 仍為 mock 灰底',
+    });
+
+    const wxavg = ((await section.locator('#wxavg').textContent()) ?? '').trim();
+    const wxbf = ((await section.locator('#wxbf').textContent()) ?? '').trim();
+    results.push({
+      name: '#wxavg / #wxbf（hero 風速數字）非空',
+      ok: wxavg.length > 0 && wxbf.length > 0,
+      detail: `wxavg="${wxavg}" wxbf="${wxbf}"`,
+    });
+
+    const rowCount = await section.locator('#mxbody .mrow').count();
+    results.push({
+      name: '#mxbody 作業矩陣渲染 7 列',
+      ok: rowCount === 7,
+      detail: `實際 ${rowCount} 列`,
+    });
+
+    return results;
+  },
 };
```

### `src/data/exchange/dispatch.ts`（新檔，187 行）

```ts
/* Dispatch live provider — 打真後端 /api/v1/dispatch/risk。
   snapshot() 仍以 mock 三情境（stable/rain/typhoon）為底：只覆蓋 stable 情境的
   nowcast/cwa/ops 燈號，rain/typhoon 兩情境維持純 demo 模擬用途不變。
   後端不在時（fetch 例外或非 2xx）整份回 mock，不影響 demo（比照 ./policy.ts）。

   ops[] 的法規/慣例規則文字（rules[]）維持前端靜態法規庫，不由後端生成；
   only now.status/now.action/cwa3/cwa6 這幾個「燈號」欄位隨 live 數值重算。
   下面 OP_THRESHOLDS 門檻表是從 src/data/mock/dispatch.json 既有 3 情境×7 作業
   （21 個資料點）反推、逐一核對吻合，但不是港務單位正式核可的規則表，正式上線前
   需域專家（港務/工安）覆核——見本次 PR 說明。 */
import type { CwaWindow, DispatchSnapshot, HorizonMetrics, LiveAnchor, OpRow, OpStatus, Provider, RainLevel } from '../types';
import dispatchMock from '../mock/dispatch.json';

const RAIN_LEVELS: RainLevel[] = ['無', '小雨', '大雨', '豪雨', '大豪雨', '超大豪雨'];
const RAIN_STOP_LEVELS: RainLevel[] = ['大雨', '豪雨', '大豪雨', '超大豪雨'];

function normalizeRainLevel(value: unknown): RainLevel {
  return typeof value === 'string' && (RAIN_LEVELS as string[]).includes(value) ? (value as RainLevel) : '無';
}

type OpId = OpRow['id'];
interface StatusInput { beaufort: number; rainLevel: RainLevel }

const OP_THRESHOLDS: Record<OpId, (i: StatusInput) => OpStatus> = {
  crane: ({ beaufort }) => (beaufort >= 6 ? 'stop' : 'ok'),
  grain: ({ rainLevel }) => (RAIN_STOP_LEVELS.includes(rainLevel) ? 'stop' : 'ok'),
  coal: ({ beaufort, rainLevel }) =>
    beaufort >= 7 ? 'stop' : beaufort >= 5 || RAIN_STOP_LEVELS.includes(rainLevel) ? 'warn' : 'ok',
  tanker: ({ beaufort }) => (beaufort >= 7 ? 'stop' : beaufort >= 5 ? 'warn' : 'ok'),
  pilot: ({ beaufort }) => (beaufort >= 7 ? 'stop' : beaufort >= 6 ? 'warn' : 'ok'),
  mooring: ({ beaufort }) => (beaufort >= 6 ? 'warn' : 'ok'),
  yard: ({ beaufort }) => (beaufort >= 7 ? 'warn' : 'ok'),
};

/* status → 沿用 mock 既有措辭；mooring/yard 的 warn 態依 beaufort 再細分既有兩種文字。 */
const OP_ACTION_TEXT: Record<OpId, (status: OpStatus, beaufort: number) => string> = {
  crane: (s) => (s === 'stop' ? '停工' : '正常'),
  grain: (s) => (s === 'stop' ? '停裝關艙' : '正常'),
  coal: (s) => (s === 'stop' ? '卸煤機固定' : s === 'warn' ? '戒備' : '正常'),
  tanker: (s) => (s === 'stop' ? '危險品船出港' : s === 'warn' ? '續作+監控' : '正常'),
  pilot: (s) => (s === 'stop' ? '停止進出港' : s === 'warn' ? '加派拖船' : '正常'),
  mooring: (s, bf) => (s === 'warn' ? (bf >= 7 ? '加派加纜 5/7' : '加派 +2') : '正常'),
  yard: (s) => (s === 'warn' ? '貨櫃加固' : '正常'),
};

function computeOpStatus(opId: OpId, input: StatusInput): OpStatus {
  return OP_THRESHOLDS[opId](input);
}

interface BackendWindField { predicted_mps?: number; beaufort?: { scale?: number } }
interface BackendAnchor {
  offset_minutes?: number;
  rain?: { amount_level?: string };
  wind_speed?: BackendWindField;
  wind_gust?: BackendWindField;
  dispatch_suggestion?: string;
  dispatch_risk_level?: string;
}
interface BackendCwaWindow { window?: string; rainLevel?: string; beaufort?: number }
interface BackendHorizonMetric { csi?: number | null; pod?: number | null; far?: number | null }
interface BackendMetrics {
  available?: boolean;
  csi?: number | null;
  pod?: number | null;
  far?: number | null;
  by_horizon?: Record<string, BackendHorizonMetric>;
}
interface BackendRiskResponse {
  forecast_anchors?: BackendAnchor[];
  cwa?: BackendCwaWindow[];
  metrics?: BackendMetrics;
}

/* 後端 dispatch_risk_level 是 5 級（normal<watch<warning<high_risk<stop，
   見 kaohsiung_microclimate_lstm/src/risk/level_mapping.py::LEVEL_ORDER），
   前端 hero 底色只有 3 態，收斂規則：normal/watch→ok、warning/high_risk→warn、stop→stop。
   無法辨識的值（欄位缺失/未知字串）回傳 undefined，呼叫端會退回既有 WXCLS[rainLevel] 查表。 */
function toRiskLevel(level: unknown): OpStatus | undefined {
  switch (level) {
    case 'normal':
    case 'watch':
      return 'ok';
    case 'warning':
    case 'high_risk':
      return 'warn';
    case 'stop':
      return 'stop';
    default:
      return undefined;
  }
}

interface Nowcast { rainLevel: RainLevel; beaufort: number; windAvg: number; windGust: number }

function toNowcast(anchor: BackendAnchor): Nowcast {
  return {
    rainLevel: normalizeRainLevel(anchor.rain?.amount_level),
    beaufort: anchor.wind_speed?.beaufort?.scale ?? 0,
    windAvg: anchor.wind_speed?.predicted_mps ?? 0,
    windGust: anchor.wind_gust?.predicted_mps ?? 0,
  };
}

function toCwaWindow(w: BackendCwaWindow, fallbackWindow: CwaWindow['window']): CwaWindow {
  return {
    window: w.window === '+3h' || w.window === '+6h' ? w.window : fallbackWindow,
    rainLevel: normalizeRainLevel(w.rainLevel),
    beaufort: typeof w.beaufort === 'number' ? w.beaufort : 0,
  };
}

function toLiveAnchor(anchor: BackendAnchor): LiveAnchor {
  return {
    offsetMinutes: anchor.offset_minutes ?? 0,
    ...toNowcast(anchor),
    suggestion: typeof anchor.dispatch_suggestion === 'string' ? anchor.dispatch_suggestion : undefined,
    riskLevel: toRiskLevel(anchor.dispatch_risk_level),
  };
}

function toHorizonMetrics(raw: Record<string, BackendHorizonMetric> | undefined): Record<'H1' | 'H2' | 'H3' | 'H4', HorizonMetrics> {
  const pick = (h: string): HorizonMetrics => {
    const v = raw?.[h];
    return { csi: v?.csi ?? null, pod: v?.pod ?? null, far: v?.far ?? null };
  };
  return { H1: pick('H1'), H2: pick('H2'), H3: pick('H3'), H4: pick('H4') };
}

function applyLiveOps(ops: OpRow[], nowcast: Nowcast, cwa: [CwaWindow, CwaWindow]): OpRow[] {
  return ops.map((op) => {
    const nowStatus = computeOpStatus(op.id, nowcast);
    return {
      ...op,
      now: { status: nowStatus, action: OP_ACTION_TEXT[op.id](nowStatus, nowcast.beaufort) },
      cwa3: computeOpStatus(op.id, cwa[0]),
      cwa6: computeOpStatus(op.id, cwa[1]),
    };
  });
}

export function createDispatchProvider(
  base: string = (import.meta as any).env?.VITE_DISPATCH_API ?? 'http://127.0.0.1:8200',
): Provider<DispatchSnapshot> {
  return {
    source: 'live',
    async snapshot() {
      const snap = structuredClone(dispatchMock as DispatchSnapshot);
      try {
        const r = await fetch(`${base}/api/v1/dispatch/risk?target_area=KHH`);
        if (!r.ok) return snap;
        const d: BackendRiskResponse = await r.json();
        const anchors = d.forecast_anchors ?? [];
        const h1 = anchors[0];
        if (!h1) return snap;

        const stable = snap.scenarios.find((s) => s.id === 'stable');
        if (!stable) return snap;

        const nowcast = toNowcast(h1);
        const cwaRaw = Array.isArray(d.cwa) ? d.cwa : [];
        const cwa: [CwaWindow, CwaWindow] = [
          cwaRaw[0] ? toCwaWindow(cwaRaw[0], '+3h') : stable.cwa[0],
          cwaRaw[1] ? toCwaWindow(cwaRaw[1], '+6h') : stable.cwa[1],
        ];

        stable.nowcast = nowcast;
        stable.cwa = cwa;
        stable.ops = applyLiveOps(stable.ops, nowcast, cwa);
        stable.liveAnchors = anchors.map(toLiveAnchor);

        // 後端第48項：/api/v1/dispatch/risk 頂層 metrics（H1 rain_probability 的 CSI/POD/FAR）。
        // available=false（報表尚未產生）時維持 mock 靜態值，不用 null 覆蓋掉展示用數字。
        const metrics = d.metrics;
        if (metrics?.available && typeof metrics.csi === 'number' && typeof metrics.pod === 'number' && typeof metrics.far === 'number') {
          stable.metrics = { csi: metrics.csi, pod: metrics.pod, far: metrics.far };
        }
        // 後端第49項：metrics.by_horizon（H1~H4逐anchor CSI/POD/FAR），拖曳時間軸用。
        if (metrics?.by_horizon) {
          stable.metricsByHorizon = toHorizonMetrics(metrics.by_horizon);
        }
      } catch {
        /* 後端不在 → 整份回 mock，demo 不掛 */
      }
      return snap;
    },
  };
}
```

### `src/data/mock/dispatch.json`

```diff
       "id": "stable",
       "label": "現況穩定",
       "nowcast": { "rainLevel": "無", "beaufort": 4, "windAvg": 6.5, "windGust": 8.1 },
-      "conclusion": "未來 90 分鐘港區天候穩定 — 全作業線正常運轉",
+      "conclusion": "未來 120 分鐘港區天候穩定 — 全作業線正常運轉",
       "cwa": [
         { "window": "+3h", "rainLevel": "無", "beaufort": 4 },
         { "window": "+6h", "rainLevel": "小雨", "beaufort": 4 }
```

### `src/data/types.ts`

```diff
-// ── dispatch（2026-07-05 spec 改版：ConvLSTM 90 分鐘單一預測 + 三情境劇本）──
+// ── dispatch（2026-07-05 spec 改版；2026-07-14 模型更名：RandomForest 120 分鐘單一預測 + 三情境劇本）──
 export type RainLevel = '無' | '小雨' | '大雨' | '豪雨' | '大豪雨' | '超大豪雨';
 export type OpStatus = 'ok' | 'warn' | 'stop';
 export type RuleTag = 'official' | 'industry';
 export interface OpRow {
   id: 'crane' | 'grain' | 'coal' | 'tanker' | 'pilot' | 'mooring' | 'yard';
   name: string;
-  now: { status: OpStatus; action: string };   // ConvLSTM 段：燈色 + 格內動作字
+  now: { status: OpStatus; action: string };   // RandomForest 段：燈色 + 格內動作字
   cwa3: OpStatus; cwa6: OpStatus;              // CWA 段：只有燈色
   rules: { text: string; basis: string; tag: RuleTag }[];
 }
 export interface DispatchCard {
   opId: string; title: string; body: string; level: OpStatus;
   badge?: { text: string; urgent: boolean };
 }
+// live provider 專用：後端單一 H 錨點的原始資料，供時間軸拖曳即時切換 hero 顯示用。
+// suggestion/riskLevel 只有 live 資料才有（來自 forecast_anchors[].dispatch_suggestion /
+// dispatch_risk_level，riskLevel 已由 provider 把後端 5 級 normal/watch/warning/high_risk/stop
+// 收斂成前端 3 態 ok/warn/stop，UI 端不需要認識後端的 5 級枚舉）。
+export interface LiveAnchor {
+  offsetMinutes: number;
+  rainLevel: RainLevel;
+  beaufort: number;
+  windAvg: number;
+  windGust: number;
+  suggestion?: string;
+  riskLevel?: OpStatus;
+}
+export interface HorizonMetrics { csi: number | null; pod: number | null; far: number | null }
+
 export interface DispatchScenario {
   id: 'stable' | 'rain' | 'typhoon';
   label: string;
   nowcast: ...;
   cwa: [CwaWindow, CwaWindow];
   ops: OpRow[];                                // 固定 7 筆
   cards: DispatchCard[];                       // 2-5 張
   metrics: { csi: number; pod: number; far: number };
+  // live provider 專用：後端 H1~H4（30/60/90/120 分鐘）原始錨點資料。
+  // 2026-07-14：時間軸拖曳（RandomForest 0-120min 區段）已接上，會依拖曳到的分鐘數
+  // 取最近的一筆即時切換 hero 數值；mock provider 不填這個欄位，拖曳時 hero 維持靜態 nowcast。
+  liveAnchors?: LiveAnchor[];
+  // live provider 專用：後端 metrics.by_horizon（第49項），H1~H4 逐錨點 CSI/POD/FAR。
+  // 2026-07-15：拖曳到 RandomForest 區段時，hero 的 CSI/POD/FAR 會依錨點切換；
+  // CWA（+3h/+6h）區段沒有對應後端指標，固定顯示「—」。mock provider 不填這個欄位。
+  metricsByHorizon?: Record<'H1' | 'H2' | 'H3' | 'H4', HorizonMetrics>;
 }
 export interface DispatchSnapshot { scenarios: DispatchScenario[] }  // 固定 3 筆
```

### `src/main.ts`　⚠️ 禁改清單例外（見上方說明）

```diff
 import { createCarbonProvider } from './data/exchange/carbon';
 import { createTwinProvider } from './data/exchange/twin';
 import { getSetting, subscribe } from './screens/settings/storage';
 import { createPolicyProvider } from './data/exchange/policy';
+import { createDispatchProvider } from './data/exchange/dispatch';
 // lg.d.ts 為 ambient 宣告（tsconfig include 已涵蓋），不需 import

 document.documentElement.setAttribute('data-lg-theme', 'dark');
 ...
 export const bg = initBackground(document.getElementById('harbor') as HTMLCanvasElement);

-// overview/dispatch/epidemic/alert 為 mock provider；carbon（Task 4）、twin（Task 8）與
-// policy（綜合對話 live）皆為 live provider（source 回報 'live'）。
+// overview/epidemic/alert 為 mock provider；carbon（Task 4）、twin（Task 8）、
+// policy（綜合對話 live）與 dispatch（微氣候派工，2026-07 接上）皆為 live provider
+// （source 回報 'live'）。
 // policy 的收件匣情報仍走 mock snapshot，只有綜合對話的自由提問打 rag-agent /api/chat。
+// dispatch 的 live 資料只覆蓋 stable 情境的 nowcast/cwa/ops 燈號，rain/typhoon 兩情境
+// 維持純 demo 模擬用途；後端不在時整份回 mock，不影響 demo（見 ./data/exchange/dispatch.ts）。
 const env = (import.meta as any).env ?? {};
 const ctx: ScreenCtx = {
   data: {
     ...
     policy: createPolicyProvider(env.VITE_POLICY_API),
     carbon: createCarbonProvider(getSetting('carbon.apiBase', '') || env.VITE_CARBON_API),
     twin: createTwinProvider(),
+    dispatch: createDispatchProvider(env.VITE_DISPATCH_API),
   },
   ui: {
     toast: (o) => window.LiquidGlass.toast(o),
```

### `src/screens/dispatch/dispatch.html`

```diff
 <div class="hero">
   <div class="wx ok anim" id="wx" style="--d:.08s">
-    <div class="win" id="wxwin">未來 90 分鐘 · 港區</div>
+    <div class="win" id="wxwin">未來 120 分鐘 · 港區</div>
     ...
       <div class="ticks">
         <span style="left:0">NOW</span>
-        <span class="srcm" style="left:20%">ConvLSTM</span>
-        <span style="left:53%">+90m</span>
+        <span class="srcm" style="left:20%">RandomForest</span>
+        <span style="left:53%">+120m</span>
         <span class="srcm" style="left:60%">CWA</span>
         <span style="left:75%">+3h</span>
         <span style="right:0">+6h</span>
   ...
   <div class="mx lg anim" data-lg style="--d:.26s">
     <div class="mhead">
       <span class="c0"></span>
-      <span class="cn" id="hN">CONVLSTM 0-90 MIN</span>
+      <span class="cn" id="hN">RANDOMFOREST 0-120 MIN</span>
       <span class="cc" id="h3">+3H</span>
       <span class="cc" id="h6">+6H</span>
     </div>
```

### `src/screens/dispatch/index.ts`（核心互動邏輯，139行變動）

```diff
 import type { Screen, ScreenCtx } from '../types';
-import type { DispatchScenario, DispatchCard, OpRow, OpStatus, RainLevel } from '../../data/types';
+import type { DispatchScenario, DispatchCard, HorizonMetrics, LiveAnchor, OpRow, OpStatus, RainLevel } from '../../data/types';
 import { screenHeader } from '../../ui/components';
 import { parseConclusion } from './conclusion';
 import { prefersReduced } from '../settings/storage';
 ...
+let inferenceId = 0;   // 情境切換/重觸發時讓晚到的重抓結果作廢，不要無預警覆蓋畫面
+
 stopInference = () => {            // 覆寫 Task 4 掛點：情境切換時中止推論動畫
+  inferenceId++;
   inferring = false;
   $('#cnt').classList.remove('running');
   paintRing();
 };
+
+/* 2026-07-14：倒數歸零時真的重打一次後端（ctx.data.dispatch.snapshot()），
+   不再是純視覺抖動——stable 情境會拿到新的 nowcast/cwa/liveAnchors，rain/typhoon
+   仍是純 mock，重抓對它們是無害的 no-op。
+   已實測後端 /api/v1/dispatch/risk 回應時間不穩定（冷啟動 ~8s，實測瀏覽器情境下偶爾 20 秒以上未回應，
+   已寫入後端規格書請查根因），前端不能無限期等待，故加 10 秒逾時：逾時或連線失敗都維持現有資料、
+   用 toast 誠實告知這次沒抓到，不假裝成功；逾時後若原本的請求晚到才回來，直接丟棄，不再套用。 */
+const REFRESH_TIMEOUT_MS = 10000;
+
 function runInference(): void {
   if (inferring) return;           // 不可重入
   inferring = true;
   $('#cnt').classList.add('running');
   remain = TOTAL;
   paintRing();
+  const id = ++inferenceId;
   later(() => {
-    inferring = false;
-    $('#cnt').classList.remove('running');
-    /* 微調：windAvg/windGust ±0.2-0.4 視覺抖動（不改燈號、不進資料，spec §7-4） */
-    const n = scn().nowcast;
-    const dir = Math.random() > 0.5 ? 1 : -1;
-    const j = (v: number) => Math.max(0, v + (Math.random() * 0.2 + 0.2) * dir);
-    $('#wxavg').textContent = j(n.windAvg).toFixed(1);
-    $('#wxgust').textContent = j(n.windGust).toFixed(1);
     const now = new Date();
-    sCtx.ui.toast({
-      title: 'ConvLSTM 已更新',
-      message: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')} 推論完成`,
-    });
-    paintRing();
+    const timeLabel = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
+    let settled = false;
+    const finish = (ok: boolean, timedOut: boolean): void => {
+      if (settled || id !== inferenceId) return;
+      settled = true;
+      inferring = false;
+      $('#cnt').classList.remove('running');
+      renderAll();
+      bubbleRefresh?.();
+      sCtx.ui.toast(
+        ok
+          ? { title: 'RandomForest 已更新', message: `${timeLabel} 重新取得後端最新預測` }
+          : {
+              title: '本次更新失敗',
+              message: `${timeLabel} ${timedOut ? '後端回應逾時（10秒）' : '後端連線失敗'}，畫面維持原有資料`,
+            },
+      );
+      paintRing();
+    };
+    const timeoutId = setTimeout(() => finish(false, true), REFRESH_TIMEOUT_MS);
+    sCtx.data.dispatch
+      .snapshot()
+      .then((snap) => {
+        clearTimeout(timeoutId);
+        if (settled || id !== inferenceId) return;   // 已逾時放棄，晚到的結果不再套用
+        scenarios = snap.scenarios;
+        finish(true, false);
+      })
+      .catch(() => {
+        clearTimeout(timeoutId);
+        finish(false, false);
+      });
   }, RM() ? 0 : 2000);
 }
 ...
-function renderHero(sc: DispatchScenario): void {
-  const n = sc.nowcast;
+interface HeroValues {
+  rainLevel: RainLevel;
+  beaufort: number;
+  windAvg: number | null;
+  windGust: number | null;
+  riskLevel?: OpStatus;   // 2026-07-15：後端 dispatch_risk_level 收斂後的值，有值時取代 WXCLS 查表
+}
+
+/* hero 大字塊的燈色/數字：拖曳時間軸時會用不同時間點的資料重繪這一段，
+   CWA 沒有精確 m/s（官方預報只給蒲福風級區間），windAvg/windGust 傳 null 時顯示「—」，
+   不假裝有精確數字。riskLevel 有值（live資料的H1~H4錨點）時優先用它決定底色，
+   否則退回 WXCLS[rainLevel] 查表（mock情境、CWA zone一律走這條路，CWA沒有dispatch_risk_level）。 */
+function renderHeroValues(n: HeroValues): void {
   const wx = $('#wx');
   wx.classList.remove('ok', 'warn', 'stop');
-  wx.classList.add(WXCLS[n.rainLevel]);
+  wx.classList.add(n.riskLevel ?? WXCLS[n.rainLevel]);
   $('#wxlvl').textContent = n.rainLevel === '無' ? '無降雨' : n.rainLevel;
   $('#wxbf').textContent = `${n.beaufort} 級`;
-  $('#wxavg').textContent = n.windAvg.toFixed(1);
-  $('#wxgust').textContent = n.windGust.toFixed(1);
-  $('#wxmet').textContent =
-    `CSI ${sc.metrics.csi.toFixed(2)} · POD ${sc.metrics.pod.toFixed(2)} · FAR ${sc.metrics.far.toFixed(2)}`;
+  $('#wxavg').textContent = n.windAvg == null ? '—' : n.windAvg.toFixed(1);
+  $('#wxgust').textContent = n.windGust == null ? '—' : n.windGust.toFixed(1);
+}
+
+function formatMetrics(m: { csi: number | null; pod: number | null; far: number | null }): string {
+  const fmt = (v: number | null) => (v == null ? '—' : v.toFixed(2));
+  return `CSI ${fmt(m.csi)} · POD ${fmt(m.pod)} · FAR ${fmt(m.far)}`;
+}
+
+const HORIZON_KEYS = ['H1', 'H2', 'H3', 'H4'] as const;
+type HorizonKey = (typeof HORIZON_KEYS)[number];
+
+/* liveAnchors（H1~H4）裡離目標分鐘數最近的一筆；平手取較早的一筆，同時回傳對應的H1~H4 key
+   （依陣列位置而非offsetMinutes數值判斷，避免依賴30/60/90/120這種寫死的分鐘數）供查
+   metricsByHorizon用。rain/typhoon情境與live取不到資料時liveAnchors是undefined，回傳null
+   交由呼叫端退回靜態nowcast。 */
+function pickAnchor(sc: DispatchScenario, minutes: number): { anchor: LiveAnchor; horizonKey: HorizonKey } | null {
+  const anchors = sc.liveAnchors;
+  if (!anchors || !anchors.length) return null;
+  let bestIdx = 0;
+  let bestDiff = Math.abs(anchors[0].offsetMinutes - minutes);
+  for (let i = 1; i < anchors.length; i++) {
+    const diff = Math.abs(anchors[i].offsetMinutes - minutes);
+    if (diff < bestDiff) { bestIdx = i; bestDiff = diff; }
+  }
+  return { anchor: anchors[bestIdx], horizonKey: HORIZON_KEYS[Math.min(bestIdx, HORIZON_KEYS.length - 1)] };
+}
+
+function metricsFor(sc: DispatchScenario, horizonKey: HorizonKey): HorizonMetrics | null {
+  return sc.metricsByHorizon?.[horizonKey] ?? null;
+}
+
+function renderHero(sc: DispatchScenario): void {
+  renderHeroValues(sc.nowcast);
+  $('#wxmet').textContent = formatMetrics(sc.metrics);
   $('#concl').innerHTML = parseConclusion(sc.conclusion);
 }
 ...
         eyebrow: '港邊人員視角 · MODULE 04',
         color: '#F5A54A',
         title: '短時微氣候 · 即時派工建議',
-        badges: ['ConvLSTM 0-90 min'],
-        source: 'mock',
+        badges: ['RandomForest 0-120 min'],
+        source: 'live',
         actionsHtml: segctlHtml(),
       }) +
 ...
       if (pct <= N_END) {
-        const min = Math.round((pct / N_END) * 90 / 5) * 5;
-        txt = `${min === 0 ? 'NOW' : `+${min} min`} · ConvLSTM · ${sc.nowcast.rainLevel}`;
+        const min = Math.round((pct / N_END) * 120 / 5) * 5;
+        const picked = pickAnchor(sc, min);
+        const anchor = picked?.anchor;
+        txt = `${min === 0 ? 'NOW' : `+${min} min`} · RandomForest · ${(anchor ?? sc.nowcast).rainLevel}`;
         zone = 'N';
+        if (anchor) {
+          renderHeroValues(anchor);
+          if (anchor.suggestion) $('#concl').textContent = anchor.suggestion;   // 沒有時維持前一次的渲染結果
+          const hm = picked ? metricsFor(sc, picked.horizonKey) : null;
+          if (hm) $('#wxmet').textContent = formatMetrics(hm);
+        }
+        $('#wxwin').textContent = `${min === 0 ? '現在' : `未來 ${min} 分鐘`} · 港區`;
       } else if (pct <= C3_END) {
         txt = `+3h · CWA · ${sc.cwa[0].rainLevel}`; zone = '3';
+        renderHeroValues({ rainLevel: sc.cwa[0].rainLevel, beaufort: sc.cwa[0].beaufort, windAvg: null, windGust: null });
+        $('#wxmet').textContent = 'CSI — · POD — · FAR —';   // CWA無對應評估指標，不假裝有
+        $('#wxwin').textContent = 'CWA官方預報 +3h · 港區';
       } else {
         txt = `+6h · CWA · ${sc.cwa[1].rainLevel}`; zone = '6';
+        renderHeroValues({ rainLevel: sc.cwa[1].rainLevel, beaufort: sc.cwa[1].beaufort, windAvg: null, windGust: null });
+        $('#wxmet').textContent = 'CSI — · POD — · FAR —';
+        $('#wxwin').textContent = 'CWA官方預報 +6h · 港區';
       }
```

### `src/screens/settings/sections/dispatch.ts`

```diff
-        { kind: 'text', key: 'dispatch.inferEndpoint', label: 'ConvLSTM 推論端點', placeholder: 'http://backend/dispatch/infer', disabled: true },
+        { kind: 'text', key: 'dispatch.inferEndpoint', label: 'RandomForest 推論端點', placeholder: 'http://backend/dispatch/infer', disabled: true },
```

### `tests/dispatch-provider.test.ts`（新檔，158行，9個測試）

```ts
import { describe, it, expect, vi } from 'vitest';
import { createDispatchProvider } from '../src/data/exchange/dispatch';
import { createMockExchange } from '../src/data/exchange/mock';

function mockRiskResponse(metrics?: { available: boolean; csi?: number; pod?: number; far?: number }) {
  return {
    metrics: {
      ...(metrics ?? { available: true, csi: 0.5524, pod: 0.6259, far: 0.1754 }),
      by_horizon: {
        H1: { csi: 0.5524, pod: 0.6259, far: 0.1754 },
        H2: { csi: 0.1111, pod: 0.2222, far: 0.3333 },
        H3: { csi: 0.3185, pod: 0.3597, far: 0.2647 },
        H4: { csi: null, pod: null, far: null },
      },
    },
    forecast_anchors: [
      {
        offset_minutes: 30,
        rain: { amount_level: '大雨' },
        wind_speed: { predicted_mps: 12.0, beaufort: { scale: 6 } },
        wind_gust: { predicted_mps: 14.0 },
        dispatch_suggestion: '建議限制吊掛、高處、臨水或其他受天氣影響較大的作業。',
        dispatch_risk_level: 'high_risk',
      },
      {
        offset_minutes: 60,
        rain: { amount_level: '大雨' },
        wind_speed: { predicted_mps: 11.0, beaufort: { scale: 6 } },
        wind_gust: { predicted_mps: 13.0 },
        dispatch_suggestion: '建議限制吊掛、高處、臨水或其他受天氣影響較大的作業。',
        dispatch_risk_level: 'warning',
      },
      {
        offset_minutes: 90,
        rain: { amount_level: '小雨' },
        wind_speed: { predicted_mps: 9.0, beaufort: { scale: 5 } },
        wind_gust: { predicted_mps: 11.0 },
        dispatch_suggestion: '可正常安排作業，持續監測天氣變化。',
        dispatch_risk_level: 'watch',
      },
      {
        offset_minutes: 120,
        rain: { amount_level: '無' },
        wind_speed: { predicted_mps: 6.0, beaufort: { scale: 4 } },
        wind_gust: { predicted_mps: 8.0 },
        dispatch_suggestion: '可正常安排作業，持續監測天氣變化。',
        dispatch_risk_level: 'normal',
      },
    ],
    cwa: [
      { window: '+3h', rainLevel: '豪雨', beaufort: 7 },
      { window: '+6h', rainLevel: '無', beaufort: 3 },
    ],
  };
}

describe('dispatch live provider', () => {
  it('live 成功時覆蓋 stable 情境的 nowcast/cwa，rain/typhoon 不受影響', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const mockSnap = await createMockExchange().dispatch.snapshot();

    const stable = s.scenarios.find((x) => x.id === 'stable')!;
    expect(stable.nowcast).toEqual({ rainLevel: '大雨', beaufort: 6, windAvg: 12.0, windGust: 14.0 });
    expect(stable.cwa).toEqual([
      { window: '+3h', rainLevel: '豪雨', beaufort: 7 },
      { window: '+6h', rainLevel: '無', beaufort: 3 },
    ]);
    expect(stable.liveAnchors).toHaveLength(4);

    const rain = s.scenarios.find((x) => x.id === 'rain')!;
    const typhoon = s.scenarios.find((x) => x.id === 'typhoon')!;
    expect(rain).toEqual(mockSnap.scenarios.find((x) => x.id === 'rain'));
    expect(typhoon).toEqual(mockSnap.scenarios.find((x) => x.id === 'typhoon'));
  });

  it('門檻表依 nowcast（beaufort 6 / 大雨）算出 stop/warn/ok 混合狀態', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const stable = s.scenarios.find((x) => x.id === 'stable')!;
    const statusOf = (id: string) => stable.ops.find((o) => o.id === id)!.now.status;

    expect(statusOf('crane')).toBe('stop');   // beaufort 6 >= 6
    expect(statusOf('grain')).toBe('stop');   // 大雨
    expect(statusOf('coal')).toBe('warn');    // beaufort 6 >= 5，< 7
    expect(statusOf('tanker')).toBe('warn');  // beaufort 6 >= 5
    expect(statusOf('pilot')).toBe('warn');   // beaufort 6 >= 6
    expect(statusOf('mooring')).toBe('warn'); // beaufort 6 >= 6
    expect(statusOf('yard')).toBe('ok');      // beaufort 6 < 7
  });

  it('cwa3/cwa6 分別依 +3h（beaufort 7）與 +6h（beaufort 3）獨立算出狀態', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const crane = s.scenarios.find((x) => x.id === 'stable')!.ops.find((o) => o.id === 'crane')!;
    expect(crane.cwa3).toBe('stop'); // +3h beaufort 7 >= 6
    expect(crane.cwa6).toBe('ok');   // +6h beaufort 3 < 6
  });

  it('metrics.available=true 時覆蓋 stable 情境的 csi/pod/far', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const stable = s.scenarios.find((x) => x.id === 'stable')!;
    expect(stable.metrics).toEqual({ csi: 0.5524, pod: 0.6259, far: 0.1754 });
  });

  it('metrics.available=false 時維持 mock 靜態 csi/pod/far，不用 null 覆蓋', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(mockRiskResponse({ available: false })))),
    );
    const s = await createDispatchProvider('http://x').snapshot();
    const mockSnap = await createMockExchange().dispatch.snapshot();
    const stable = s.scenarios.find((x) => x.id === 'stable')!;
    const mockStable = mockSnap.scenarios.find((x) => x.id === 'stable')!;
    expect(stable.metrics).toEqual(mockStable.metrics);
  });

  it('liveAnchors 四筆都帶有正確的 suggestion 與收斂後的 riskLevel', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const anchors = s.scenarios.find((x) => x.id === 'stable')!.liveAnchors!;

    expect(anchors[0].suggestion).toBe('建議限制吊掛、高處、臨水或其他受天氣影響較大的作業。');
    expect(anchors[0].riskLevel).toBe('warn');   // high_risk → warn
    expect(anchors[1].riskLevel).toBe('warn');   // warning → warn
    expect(anchors[2].riskLevel).toBe('ok');     // watch → ok
    expect(anchors[3].riskLevel).toBe('ok');     // normal → ok
    expect(anchors[3].suggestion).toBe('可正常安排作業，持續監測天氣變化。');
  });

  it('stable.metricsByHorizon 四組數字正確透傳（含 null）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(mockRiskResponse()))));
    const s = await createDispatchProvider('http://x').snapshot();
    const stable = s.scenarios.find((x) => x.id === 'stable')!;

    expect(stable.metricsByHorizon).toEqual({
      H1: { csi: 0.5524, pod: 0.6259, far: 0.1754 },
      H2: { csi: 0.1111, pod: 0.2222, far: 0.3333 },
      H3: { csi: 0.3185, pod: 0.3597, far: 0.2647 },
      H4: { csi: null, pod: null, far: null },
    });
  });

  it('後端不在時（fetch 例外）整份回傳純 mock，不拋錯', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('refused'); }));
    const s = await createDispatchProvider('http://x').snapshot();
    const mockSnap = await createMockExchange().dispatch.snapshot();
    expect(s).toEqual(mockSnap);
  });

  it('後端回非 2xx 時整份回傳純 mock', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 503 })));
    const s = await createDispatchProvider('http://x').snapshot();
    const mockSnap = await createMockExchange().dispatch.snapshot();
    expect(s).toEqual(mockSnap);
  });
});
```
