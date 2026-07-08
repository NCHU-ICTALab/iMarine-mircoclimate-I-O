from __future__ import annotations

from datetime import timedelta
from html import escape
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.collectors.cwa import collect as collect_cwa
from app.collectors.cwa_history import (
    collect_history as collect_codis_history,
    latest_codis_history_end,
)
from app.collectors.cwa_historyapi import (
    ALLOWED_HISTORY_HOURS,
    collect_historyapi,
    inspect_historyapi,
)
from app.collectors.cwa_marine_history import collect_marine_history, inspect_marine_history
from app.collectors.twport import collect
from app.config import settings
from app.contracts import current_response, forecast_response, history_response, schema_response
from app.forecast_engine import build_wind_forecast
from app.storage import ObservationStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="TWPort Microclimate API", version="0.1.0")
store = ObservationStore(settings.database_path)
REPO_ROOT = Path(__file__).resolve().parents[1]
MICROCLIMATE_PROJECT_ROOT = REPO_ROOT / "kaohsiung_microclimate_lstm"


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return render_dashboard(store.data_status())


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "collector": {
            "twport": "configured",
            "cwa": "configured" if settings.cwa_api_key else "missing CWA_API_KEY",
        },
        "latest_fetched_at": store.latest_fetched_at(),
        "row_count": store.count(),
    }


@app.get("/api/v1/schema")
def api_v1_schema() -> dict:
    return schema_response()


@app.get("/api/v1/dispatch/risk")
def dispatch_risk_v1(target_station_id: str = Query("467441")) -> dict:
    return build_dispatch_risk_response(target_station_id)


def build_dispatch_risk_response(target_station_id: str) -> dict:
    data_path = MICROCLIMATE_PROJECT_ROOT / "data" / "raw" / "observed_hourly" / f"{target_station_id}.csv"
    config_path = MICROCLIMATE_PROJECT_ROOT / "config.yaml"
    if not data_path.exists():
        raise HTTPException(status_code=404, detail=f"No observed hourly data for target_station_id={target_station_id}")
    if not config_path.exists():
        raise HTTPException(status_code=503, detail="Microclimate dispatch risk config is missing")

    try:
        from kaohsiung_microclimate_lstm.src.predict import predict_dispatch_risk_v252
        from kaohsiung_microclimate_lstm.src.preprocess import load_observations

        observations = load_observations(data_path)
        return predict_dispatch_risk_v252(
            target_station_id=target_station_id,
            recent_observations=observations,
            config_path=str(config_path),
            project_root=MICROCLIMATE_PROJECT_ROOT,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("dispatch risk prediction failed for station %s", target_station_id)
        raise HTTPException(status_code=503, detail=f"Dispatch risk prediction failed: {exc}") from exc


@app.post("/admin/fetch")
async def fetch(wind_mode: int = Query(1)) -> dict:
    if wind_mode not in (1, 10, 15):
        return {"error": "wind_mode must be one of 1, 10, 15"}
    observations = await collect(wind_mode=int(wind_mode))
    written = store.upsert_many(observations)
    return {"written": written, "wind_mode": wind_mode}


@app.post("/admin/fetch-cwa")
async def fetch_cwa() -> dict:
    observations = await collect_cwa()
    written = store.upsert_many(observations)
    return {
        "written": written,
        "source": "cwa",
        "message": "CWA_API_KEY is not configured" if not settings.cwa_api_key else None,
    }


@app.get("/cwa/history")
async def cwa_history(hours: int = Query(24), source: str = Query("official_land")) -> dict:
    if hours not in ALLOWED_HISTORY_HOURS:
        return {"error": f"hours must be one of {ALLOWED_HISTORY_HOURS}"}
    if source not in ("official_land", "marine", "codis_fallback", "all"):
        return {"error": "source must be one of official_land, marine, codis_fallback, all"}

    observations = []
    notes = []
    if source in ("official_land", "all"):
        land_observations = await collect_historyapi(hours=hours)
        observations.extend(land_observations)
        notes.append("official_land uses CWA historyapi getMetadata/getData and is fetched on demand without saving to SQLite.")
    if source in ("marine", "all"):
        marine_observations = await collect_marine_history(hours=hours)
        observations.extend(marine_observations)
        notes.append("marine uses CWA O-B0075-001 rolling 48-hour sea surface observations and is fetched on demand without saving to SQLite.")
    if source == "codis_fallback":
        codis_observations = await collect_codis_history(hours=hours)
        observations.extend(codis_observations)
        latest_history_end = latest_codis_history_end()
        notes.append(
            "codis_fallback uses CODiS page-backed station data, usually up to the previous complete day; use only as fallback."
        )
        query_start = (latest_history_end.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)).isoformat()
        query_end = latest_history_end.isoformat()
    else:
        query_end_dt = max((obs.obs_time for obs in observations), default=None)
        query_start_dt = min((obs.obs_time for obs in observations), default=None)
        query_start = query_start_dt.isoformat() if query_start_dt else None
        query_end = query_end_dt.isoformat() if query_end_dt else None

    observations.sort(key=lambda obs: (obs.source, obs.station_id, obs.obs_time))
    return {
        "source": source,
        "hours": hours,
        "query_start": query_start,
        "query_end": query_end,
        "land_stations": settings.cwa_station_name_list,
        "marine_station_ids": settings.cwa_marine_station_id_list,
        "codis_stations": settings.cwa_history_station_specs,
        "count": len(observations),
        "data": [obs.to_dict() for obs in observations],
        "note": " ".join(notes),
    }


@app.get("/api/v1/cwa/history")
async def cwa_history_v1(hours: int = Query(24), source: str = Query("official_land")) -> dict:
    if hours not in ALLOWED_HISTORY_HOURS:
        return {"error": f"hours must be one of {ALLOWED_HISTORY_HOURS}"}
    if source not in ("official_land", "marine", "codis_fallback", "all"):
        return {"error": "source must be one of official_land, marine, codis_fallback, all"}

    observations = []
    notes = []
    if source in ("official_land", "all"):
        observations.extend(await collect_historyapi(hours=hours))
        notes.append("official_land uses CWA historyapi getMetadata/getData.")
    if source in ("marine", "all"):
        observations.extend(await collect_marine_history(hours=hours))
        notes.append("marine uses CWA O-B0075-001 rolling 48-hour sea surface observations.")
    if source == "codis_fallback":
        observations.extend(await collect_codis_history(hours=hours))
        latest_history_end = latest_codis_history_end()
        notes.append("codis_fallback is retained for cold-start or long-outage fallback only.")
        query_start = (latest_history_end.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)).isoformat()
        query_end = latest_history_end.isoformat()
    else:
        query_end_dt = max((obs.obs_time for obs in observations), default=None)
        query_start_dt = min((obs.obs_time for obs in observations), default=None)
        query_start = query_start_dt.isoformat() if query_start_dt else None
        query_end = query_end_dt.isoformat() if query_end_dt else None

    observations.sort(key=lambda obs: (obs.source, obs.station_id, obs.obs_time))
    return history_response(
        source=source,
        hours=hours,
        observations=observations,
        query_start=query_start,
        query_end=query_end,
        note=" ".join(notes),
        source_config={
            "land_stations": settings.cwa_station_name_list,
            "marine_station_ids": settings.cwa_marine_station_id_list,
            "codis_stations": settings.cwa_history_station_specs,
        },
    )


@app.get("/cwa/history/diagnostics")
async def cwa_history_diagnostics(hours: int = Query(6)) -> dict:
    if hours not in ALLOWED_HISTORY_HOURS:
        return {"error": f"hours must be one of {ALLOWED_HISTORY_HOURS}"}
    historyapi_status = await inspect_historyapi(hours=hours)
    marine_status = await inspect_marine_history()
    return {
        "hours": hours,
        "official_land": historyapi_status,
        "marine": marine_status,
        "codis_fallback": {
            "role": "fallback_only",
            "note": "CODiS is retained for cold-start or long-outage fallback, not normal polling.",
            "stations": settings.cwa_history_station_specs,
        },
    }


@app.post("/admin/fetch-all")
async def fetch_all(wind_mode: int = Query(1)) -> dict:
    if wind_mode not in (1, 10, 15):
        return {"error": "wind_mode must be one of 1, 10, 15"}
    twport_observations = await collect(wind_mode=int(wind_mode))
    cwa_observations = await collect_cwa()
    written = store.upsert_many(twport_observations + cwa_observations)
    return {
        "written": written,
        "twport_count": len(twport_observations),
        "cwa_count": len(cwa_observations),
        "wind_mode": wind_mode,
    }


@app.get("/microclimate/current")
def current() -> dict:
    observations = store.latest_by_device_type()
    grouped: dict[str, list[dict]] = {}
    for obs in observations:
        grouped.setdefault(obs.device_type, []).append(obs.to_dict())
    return {
        "data": grouped,
        "data_quality": {
            "stale_count": sum(1 for obs in observations if obs.stale),
            "total_count": len(observations),
            "contains_stale": any(obs.stale for obs in observations),
        },
    }


@app.get("/api/v1/microclimate/current")
def current_v1() -> dict:
    return current_response(store.latest_by_device_type())


@app.get("/microclimate/status")
def status() -> dict:
    return store.data_status()


@app.get("/microclimate/forecast")
def forecast(minutes: int = Query(90, ge=0, le=90)) -> dict:
    forecasts = build_wind_forecast(store.recent_history(hours=2), minutes=minutes)
    return {
        "minutes": minutes,
        "data": [obs.to_dict() for obs in forecasts],
        "data_quality": {
            "points": len(forecasts),
            "method": "linear wind_speed projection; persistence when history is insufficient",
        },
    }


@app.get("/api/v1/microclimate/forecast")
def forecast_v1(minutes: int = Query(90, ge=0, le=90)) -> dict:
    forecasts = build_wind_forecast(store.recent_history(hours=2), minutes=minutes)
    return forecast_response(minutes, forecasts)


def render_dashboard(status_data: dict) -> str:
    overall = status_data["overall"]
    status_class = "ok" if overall["is_current"] else "warn"
    status_text = "資料在有效時間內" if overall["is_current"] else "有資料已過期或尚未抓取"
    group_rows = "\n".join(render_group_row(item) for item in status_data["groups"])
    station_rows = "\n".join(render_station_row(item) for item in status_data["stations"])
    stale_policy_text = (
        f'{status_data["stale_after_minutes"]} 分鐘'
        if status_data.get("stale_after_minutes") is not None
        else "依資料類型判斷"
    )

    if not group_rows:
        group_rows = '<tr><td colspan="11" class="empty">目前資料庫沒有觀測資料</td></tr>'
    if not station_rows:
        station_rows = '<tr><td colspan="10" class="empty">目前資料庫沒有測站資料</td></tr>'

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>高雄港微氣候資料狀態</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #17202a;
      --muted: #5c6675;
      --ok: #0f7b4f;
      --ok-bg: #e7f5ef;
      --warn: #a43f18;
      --warn-bg: #fff1e8;
      --accent: #1f6feb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", "Noto Sans TC", Arial, sans-serif;
      line-height: 1.5;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    .wrap {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 0;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    a.button,
    button {{
      color: #ffffff;
      background: var(--accent);
      border: 0;
      text-decoration: none;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 14px;
      white-space: nowrap;
      cursor: pointer;
      font-family: inherit;
    }}
    button.secondary {{
      background: #435366;
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.66;
    }}
    main {{ padding: 20px 0 40px; }}
    .controls {{
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .control-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .control-panel h2 {{
      margin-bottom: 8px;
    }}
    .button-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .segmented {{
      display: inline-flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 4px;
      background: #eef1f5;
      border-radius: 8px;
    }}
    .segmented input {{
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }}
    .segmented label {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      color: var(--muted);
      font-size: 14px;
      font-weight: 600;
    }}
    .segmented input:checked + label {{
      background: #ffffff;
      color: var(--text);
      box-shadow: 0 0 0 1px var(--line);
    }}
    #operation-status {{
      min-height: 24px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }}
    #operation-status.ok {{ color: var(--ok); }}
    #operation-status.warn {{ color: var(--warn); }}
    .history-result {{
      margin-top: 10px;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfe;
    }}
    .history-result table {{
      min-width: 720px;
    }}
    .history-result td,
    .history-result th {{
      font-size: 13px;
      padding: 8px 10px;
    }}
    .source-guide {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }}
    .source-guide div {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfe;
    }}
    .source-guide strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 14px;
    }}
    .source-guide span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 96px;
    }}
    .metric strong {{
      display: block;
      font-size: 28px;
      line-height: 1.1;
      margin-top: 8px;
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
    }}
    .status-banner {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 18px;
      border: 1px solid var(--line);
    }}
    .status-banner.ok {{ background: var(--ok-bg); color: var(--ok); }}
    .status-banner.warn {{ background: var(--warn-bg); color: var(--warn); }}
    section {{
      margin-top: 18px;
    }}
    h2 {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      color: var(--muted);
      background: #fafbfc;
      font-weight: 600;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
    }}
    .pill.ok {{ background: var(--ok-bg); color: var(--ok); }}
    .pill.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .pill.outage {{ background: #f4e8ff; color: #6f35a5; }}
    .muted {{ color: var(--muted); }}
    .empty {{
      color: var(--muted);
      text-align: center;
      padding: 24px;
    }}
    @media (max-width: 820px) {{
      .top {{ align-items: flex-start; flex-direction: column; }}
      .controls {{ grid-template-columns: 1fr; }}
      .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .source-guide {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 520px) {{
      .wrap {{ width: min(100% - 20px, 1180px); }}
      .summary {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap top">
      <div>
        <h1>高雄港微氣候資料狀態</h1>
        <div class="muted">每 60 秒自動更新，時間以 Asia/Taipei 顯示</div>
      </div>
      <nav class="actions" aria-label="快捷操作">
        <a class="button" href="/docs">Swagger</a>
        <a class="button" href="/api/v1/schema">v1 Schema</a>
        <a class="button" href="/microclimate/status">狀態 JSON</a>
        <a class="button" href="/api/v1/microclimate/current">最新資料 JSON</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <div class="status-banner {status_class}">
      <strong>{escape(status_text)}</strong>
      <span>過期門檻：{stale_policy_text}</span>
    </div>
    <section class="controls" aria-label="資料更新操作">
      <div class="control-panel">
        <h2>資料更新</h2>
        <div class="button-row">
          <button type="button" data-fetch-url="/admin/fetch-all" data-needs-mode="true">更新全部</button>
          <button type="button" data-fetch-url="/admin/fetch" data-needs-mode="true" class="secondary">只更新 TWPort</button>
          <button type="button" data-fetch-url="/admin/fetch-cwa" class="secondary">只更新 CWA</button>
          <button type="button" id="reload-page" class="secondary">重新整理狀態</button>
        </div>
        <div id="operation-status" role="status" aria-live="polite"></div>
      </div>
      <div class="control-panel">
        <h2>TWPort 風速時間尺度</h2>
        <div class="segmented" role="radiogroup" aria-label="TWPort 風速時間尺度">
          <input id="wind-mode-1" name="wind-mode" type="radio" value="1" checked>
          <label for="wind-mode-1">1 分鐘</label>
          <input id="wind-mode-10" name="wind-mode" type="radio" value="10">
          <label for="wind-mode-10">10 分鐘</label>
          <input id="wind-mode-15" name="wind-mode" type="radio" value="15">
          <label for="wind-mode-15">15 分鐘</label>
        </div>
        <div class="muted">更新全部或 TWPort 時會套用這個時間尺度。</div>
      </div>
    </section>
    <section class="control-panel" aria-label="CWA 歷史資料查詢">
      <h2>CWA 歷史資料</h2>
      <div class="button-row">
        <div class="segmented" role="radiogroup" aria-label="CWA 歷史資料時間範圍">
          <input id="cwa-history-6" name="cwa-history-hours" type="radio" value="6">
          <label for="cwa-history-6">6 小時</label>
          <input id="cwa-history-12" name="cwa-history-hours" type="radio" value="12">
          <label for="cwa-history-12">12 小時</label>
          <input id="cwa-history-24" name="cwa-history-hours" type="radio" value="24" checked>
          <label for="cwa-history-24">24 小時</label>
          <input id="cwa-history-48" name="cwa-history-hours" type="radio" value="48">
          <label for="cwa-history-48">48 小時</label>
        </div>
        <div class="segmented" role="radiogroup" aria-label="CWA 歷史資料類型">
          <input id="cwa-source-land" name="cwa-history-source" type="radio" value="official_land" checked>
          <label for="cwa-source-land">陸上氣象</label>
          <input id="cwa-source-marine" name="cwa-history-source" type="radio" value="marine">
          <label for="cwa-source-marine">海象潮位</label>
          <input id="cwa-source-all" name="cwa-history-source" type="radio" value="all">
          <label for="cwa-source-all">官方全部</label>
          <input id="cwa-source-codis" name="cwa-history-source" type="radio" value="codis_fallback">
          <label for="cwa-source-codis">CODiS 備援</label>
        </div>
        <button type="button" id="load-cwa-history">查詢 CWA 歷史</button>
        <a class="button" id="open-cwa-history-json" href="/cwa/history?hours=24&source=official_land" target="_blank">開啟 JSON</a>
        <a class="button" href="/cwa/history/diagnostics" target="_blank">診斷 JSON</a>
      </div>
      <div class="muted">即時向 CWA 查詢，不寫入 SQLite。陸上氣象優先用 <code>historyapi</code>，海象潮位用 <code>O-B0075-001</code>，CODiS 僅作冷啟動或長停機備援。</div>
      <div class="source-guide" aria-label="CWA 歷史資料來源說明">
        <div>
          <strong>陸上氣象</strong>
          <span>CWA historyapi / O-A0001-001，通常逐時；適合風、雨量、溫度、濕度、氣壓。</span>
        </div>
        <div>
          <strong>海象潮位</strong>
          <span>CWA O-B0075-001，滾動 48 小時；規格建議約每 4 小時同步，資料列多為逐時。</span>
        </div>
        <div>
          <strong>CODiS 備援</strong>
          <span>只在官方歷史來源查不到、冷啟動或長時間停機後使用；通常到上一個完整日。</span>
        </div>
      </div>
      <div id="cwa-history-status" role="status" aria-live="polite"></div>
      <div class="history-result" id="cwa-history-result"></div>
    </section>
    <div class="summary" aria-label="資料總覽">
      <div class="metric"><span class="label">最新測站資料</span><strong>{overall["latest_station_count"]}</strong></div>
      <div class="metric"><span class="label">過期測站</span><strong>{overall["current_stale_count"]}</strong></div>
      <div class="metric"><span class="label">資料總筆數</span><strong>{overall["total_rows"]}</strong></div>
      <div class="metric"><span class="label">最新抓取距今</span><strong>{format_minutes(overall["latest_fetch_age_minutes"])}</strong></div>
    </div>
    <section>
      <h2>資料類型總覽</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>狀態</th>
              <th>來源</th>
              <th>類型</th>
              <th>預期更新</th>
              <th>過期門檻</th>
              <th>測站</th>
              <th>總筆數</th>
              <th>最新觀測時間</th>
              <th>觀測距今</th>
              <th>最新抓取時間</th>
              <th>抓取距今</th>
            </tr>
          </thead>
          <tbody>{group_rows}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>最新測站明細</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>狀態</th>
              <th>來源</th>
              <th>類型</th>
              <th>預期更新</th>
              <th>過期門檻</th>
              <th>測站</th>
              <th>位置</th>
              <th>觀測時間</th>
              <th>觀測距今</th>
              <th>抓取時間</th>
            </tr>
          </thead>
          <tbody>{station_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const operationStatus = document.getElementById("operation-status");
    const buttons = Array.from(document.querySelectorAll("button[data-fetch-url]"));
    const reloadButton = document.getElementById("reload-page");
    const cwaHistoryButton = document.getElementById("load-cwa-history");
    const cwaHistoryStatus = document.getElementById("cwa-history-status");
    const cwaHistoryResult = document.getElementById("cwa-history-result");
    const cwaHistoryJsonLink = document.getElementById("open-cwa-history-json");

    function selectedWindMode() {{
      const selected = document.querySelector("input[name='wind-mode']:checked");
      return selected ? selected.value : "1";
    }}

    function setBusy(isBusy) {{
      buttons.forEach((button) => {{
        button.disabled = isBusy;
      }});
      reloadButton.disabled = isBusy;
    }}

    function setStatus(message, kind) {{
      operationStatus.textContent = message;
      operationStatus.className = kind || "";
    }}

    async function runFetch(button) {{
      const url = new URL(button.dataset.fetchUrl, window.location.origin);
      if (button.dataset.needsMode === "true") {{
        url.searchParams.set("wind_mode", selectedWindMode());
      }}
      setBusy(true);
      setStatus("正在更新資料...", "");
      try {{
        const response = await fetch(url, {{ method: "POST" }});
        const body = await response.json();
        if (!response.ok || body.error) {{
          throw new Error(body.error || `HTTP ${{response.status}}`);
        }}
        const written = typeof body.written === "number" ? `，寫入 ${{body.written}} 筆` : "";
        setStatus(`更新完成${{written}}，正在刷新狀態...`, "ok");
        window.setTimeout(() => window.location.reload(), 700);
      }} catch (error) {{
        setStatus(`更新失敗：${{error.message}}`, "warn");
      }} finally {{
        setBusy(false);
      }}
    }}

    buttons.forEach((button) => {{
      button.addEventListener("click", () => runFetch(button));
    }});
    reloadButton.addEventListener("click", () => window.location.reload());

    function selectedHistoryHours() {{
      const selected = document.querySelector("input[name='cwa-history-hours']:checked");
      return selected ? selected.value : "24";
    }}

    function selectedHistorySource() {{
      const selected = document.querySelector("input[name='cwa-history-source']:checked");
      return selected ? selected.value : "official_land";
    }}

    function updateHistoryLink() {{
      cwaHistoryJsonLink.href = `/cwa/history?hours=${{selectedHistoryHours()}}&source=${{selectedHistorySource()}}`;
    }}

    function renderHistoryTable(payload) {{
      if (!payload.data || payload.data.length === 0) {{
        cwaHistoryResult.innerHTML = '<div class="empty">查無 CWA 歷史資料</div>';
        return;
      }}
      const rows = payload.data.slice(-120).reverse().map((row) => `
        <tr>
          <td>${{row.source}}</td>
          <td>${{row.device_type}}</td>
          <td>${{row.station_name}}</td>
          <td>${{String(row.obs_time).replace("T", " ")}}</td>
          <td>${{formatCell(row.air_temperature)}}</td>
          <td>${{formatCell(row.relative_humidity)}}</td>
          <td>${{formatCell(row.precipitation_1hr)}}</td>
          <td>${{formatCell(row.wind_speed)}}</td>
          <td>${{formatCell(row.wind_gust)}}</td>
          <td>${{formatCell(row.tide_level)}}</td>
          <td>${{formatCell(row.wave_height)}}</td>
          <td>${{formatCell(row.current_speed)}}</td>
        </tr>
      `).join("");
      cwaHistoryResult.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>來源</th>
              <th>類型</th>
              <th>測站</th>
              <th>觀測時間</th>
              <th>氣溫</th>
              <th>濕度</th>
              <th>雨量</th>
              <th>風速</th>
              <th>陣風</th>
              <th>潮位</th>
              <th>浪高</th>
              <th>海流</th>
            </tr>
          </thead>
          <tbody>${{rows}}</tbody>
        </table>
      `;
    }}

    function formatCell(value) {{
      return value === null || value === undefined ? "-" : value;
    }}

    async function loadCwaHistory() {{
      const hours = selectedHistoryHours();
      const source = selectedHistorySource();
      updateHistoryLink();
      cwaHistoryButton.disabled = true;
      cwaHistoryStatus.textContent = "正在查詢 CWA 歷史資料...";
      cwaHistoryStatus.className = "";
      try {{
        const response = await fetch(`/cwa/history?hours=${{hours}}&source=${{source}}`);
        const payload = await response.json();
        if (!response.ok || payload.error) {{
          throw new Error(payload.error || `HTTP ${{response.status}}`);
        }}
        cwaHistoryStatus.textContent = `查詢完成：${{payload.count}} 筆，實際回傳區間 ${{String(payload.query_start || "-").replace("T", " ")}} 到 ${{String(payload.query_end || "-").replace("T", " ")}}`;
        cwaHistoryStatus.className = "ok";
        renderHistoryTable(payload);
      }} catch (error) {{
        cwaHistoryStatus.textContent = `查詢失敗：${{error.message}}`;
        cwaHistoryStatus.className = "warn";
      }} finally {{
        cwaHistoryButton.disabled = false;
      }}
    }}

    document.querySelectorAll("input[name='cwa-history-hours']").forEach((input) => {{
      input.addEventListener("change", updateHistoryLink);
    }});
    document.querySelectorAll("input[name='cwa-history-source']").forEach((input) => {{
      input.addEventListener("change", updateHistoryLink);
    }});
    cwaHistoryButton.addEventListener("click", loadCwaHistory);
    updateHistoryLink();
  </script>
</body>
</html>"""


def render_group_row(item: dict) -> str:
    level = "outage" if item["outage_count"] else ("current" if item["is_current"] else "stale")
    return f"""<tr>
  <td>{status_pill(level)}</td>
  <td>{escape(str(item["source"]))}</td>
  <td>{escape(str(item["device_type"]))}</td>
  <td>{escape(str(item["expected_update_interval"]))}<div class="muted">{escape(str(item["policy_note"]))}</div></td>
  <td>{format_minutes(item["threshold_minutes"])}</td>
  <td>{item["latest_station_count"]} / {item["station_count"]}</td>
  <td>{item["row_count"]}</td>
  <td>{format_time(item["latest_obs_time"])}</td>
  <td>{format_minutes(item["latest_obs_age_minutes"])}</td>
  <td>{format_time(item["latest_fetched_at"])}</td>
  <td>{format_minutes(item["latest_fetch_age_minutes"])}</td>
</tr>"""


def render_station_row(item: dict) -> str:
    return f"""<tr>
  <td>{status_pill(item["status_level"], item["status_label"])}</td>
  <td>{escape(str(item["source"]))}</td>
  <td>{escape(str(item["device_type"]))}</td>
  <td>{escape(str(item["expected_update_interval"]))}</td>
  <td>{format_minutes(item["threshold_minutes"])}</td>
  <td>{escape(str(item["station_name"]))}<div class="muted">{escape(str(item["station_id"]))}</div></td>
  <td>{escape(str(item["location"] or ""))}</td>
  <td>{format_time(item["obs_time"])}</td>
  <td>{format_minutes(item["obs_age_minutes"])}</td>
  <td>{format_time(item["fetched_at"])}</td>
</tr>"""


def status_pill(level: str, label: str | None = None) -> str:
    if level == "current":
        return '<span class="pill ok">最新</span>'
    if level == "outage":
        return '<span class="pill outage">停擺</span>'
    return f'<span class="pill warn">{escape(label or "過期")}</span>'


def format_minutes(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 60:
        return f"{value} 分"
    hours = value // 60
    minutes = value % 60
    return f"{hours} 時 {minutes} 分"


def format_time(value: str | None) -> str:
    if not value:
        return "-"
    return escape(value.replace("T", " "))
