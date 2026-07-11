from __future__ import annotations

from datetime import timedelta
from html import escape
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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
from app.contracts import (
    appendix_spec_response,
    api_spec_response,
    current_response,
    forecast_response,
    data_spec_response,
    deployment_spec_response,
    evaluation_spec_response,
    feature_spec_response,
    history_response,
    model_spec_response,
    schedule_spec_response,
    schema_response,
    system_info_response,
    system_requirements_response,
    testing_spec_response,
)
from app.forecast_engine import build_wind_forecast
from app.fetch_microclimate import run_microclimate_source_fetch
from app.scheduler import MicroclimateFetchScheduler
from app.storage import ObservationStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="TWPort Microclimate API", version="0.1.0")

_cors_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ObservationStore(settings.database_path)
REPO_ROOT = Path(__file__).resolve().parents[1]
MICROCLIMATE_PROJECT_ROOT = REPO_ROOT / "kaohsiung_microclimate_lstm"
MICROCLIMATE_CONFIG_PATH = MICROCLIMATE_PROJECT_ROOT / "config.yaml"
fetch_scheduler = MicroclimateFetchScheduler(MICROCLIMATE_PROJECT_ROOT, MICROCLIMATE_CONFIG_PATH)


@app.on_event("startup")
def startup_scheduler() -> None:
    fetch_scheduler.start()


@app.on_event("shutdown")
def shutdown_scheduler() -> None:
    fetch_scheduler.shutdown()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return render_dashboard(store.data_status())


@app.get("/dispatch-risk-demo", response_class=HTMLResponse)
def dispatch_risk_demo() -> str:
    return render_dispatch_risk_demo()


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


@app.get("/api/v1/system/info")
def api_v1_system_info() -> dict:
    return system_info_response()


@app.get("/api/v1/system/requirements")
def api_v1_system_requirements() -> dict:
    return system_requirements_response()


@app.get("/api/v1/system/data-spec")
def api_v1_system_data_spec() -> dict:
    return data_spec_response()


@app.get("/api/v1/system/feature-spec")
def api_v1_system_feature_spec() -> dict:
    return feature_spec_response()


@app.get("/api/v1/system/model-spec")
def api_v1_system_model_spec() -> dict:
    return model_spec_response()


@app.get("/api/v1/system/evaluation-spec")
def api_v1_system_evaluation_spec() -> dict:
    return evaluation_spec_response()


@app.get("/api/v1/system/api-spec")
def api_v1_system_api_spec() -> dict:
    return api_spec_response()


@app.get("/api/v1/system/deployment-spec")
def api_v1_system_deployment_spec() -> dict:
    return deployment_spec_response()


@app.get("/api/v1/system/testing-spec")
def api_v1_system_testing_spec() -> dict:
    return testing_spec_response()


@app.get("/api/v1/system/schedule-spec")
def api_v1_system_schedule_spec() -> dict:
    return schedule_spec_response()


@app.get("/api/v1/system/appendix-spec")
def api_v1_system_appendix_spec() -> dict:
    return appendix_spec_response()


@app.get("/api/v1/dispatch/risk")
def dispatch_risk_v1(
    target_area: str = Query("KHH"),
    target_station_id: str | None = Query(None),
    refresh_port_local: bool = Query(False),
    no_realtime_khwd_mode: bool = Query(False),
) -> dict:
    return build_dispatch_risk_response(
        target_area=target_area,
        target_station_id=target_station_id,
        refresh_port_local=refresh_port_local,
        no_realtime_khwd_mode=no_realtime_khwd_mode,
    )


@app.get("/api/v1/dispatch/model-status")
def dispatch_model_status_v1(target_area: str = Query("KHH")) -> dict:
    config_path = MICROCLIMATE_PROJECT_ROOT / "config.yaml"
    try:
        from kaohsiung_microclimate_lstm.src.predict import build_dispatch_model_status_v34

        return build_dispatch_model_status_v34(
            config_path=str(config_path),
            project_root=MICROCLIMATE_PROJECT_ROOT,
            target_area=target_area,
        )
    except Exception as exc:
        logging.exception("dispatch model status failed for target area %s", target_area)
        raise HTTPException(status_code=503, detail=f"Dispatch model status failed: {exc}") from exc


@app.get("/api/v1/dispatch/station-usage")
def dispatch_station_usage_v1(
    target_area: str = Query("KHH"),
    no_realtime_khwd_mode: bool = Query(False),
) -> dict:
    payload = build_dispatch_risk_response(target_area=target_area, no_realtime_khwd_mode=no_realtime_khwd_mode)
    return {
        "model_version": payload.get("model_version"),
        "target_area": target_area,
        "prediction_mode": payload.get("prediction_mode"),
        "current_station_usage": payload.get("current_station_usage", {}),
        "station_display_rows": payload.get("station_display_rows", []),
        "trace": {
            "selection_case_id": payload.get("trace", {}).get("selection_case_id"),
            "467441_used_as_core_station": payload.get("trace", {}).get("467441_used_as_core_station"),
            "nearby_cwa_used_as_port_local_core": payload.get("trace", {}).get("nearby_cwa_used_as_port_local_core"),
        },
    }


@app.get("/api/v1/dispatch/system-audit")
def dispatch_system_audit_v1(target_area: str = Query("KHH")) -> dict:
    config_path = MICROCLIMATE_PROJECT_ROOT / "config.yaml"
    try:
        from kaohsiung_microclimate_lstm.src.system_audit import build_v35_system_audit

        return build_v35_system_audit(
            config_path=str(config_path),
            target_area=target_area,
            report_dir=MICROCLIMATE_PROJECT_ROOT / "results" / "dispatch_risk_v35",
            project_root=MICROCLIMATE_PROJECT_ROOT,
        )
    except Exception as exc:
        logging.exception("dispatch system audit failed for target area %s", target_area)
        raise HTTPException(status_code=503, detail=f"Dispatch system audit failed: {exc}") from exc


def build_dispatch_risk_response(
    target_area: str = "KHH",
    target_station_id: str | None = None,
    refresh_port_local: bool = False,
    no_realtime_khwd_mode: bool = False,
) -> dict:
    fallback_station_id = "467441"
    data_path = MICROCLIMATE_PROJECT_ROOT / "data" / "raw" / "observed_hourly" / f"{fallback_station_id}.csv"
    config_path = MICROCLIMATE_PROJECT_ROOT / "config.yaml"
    if not data_path.exists():
        raise HTTPException(status_code=404, detail=f"No observed hourly data for fallback_station_id={fallback_station_id}")
    if not config_path.exists():
        raise HTTPException(status_code=503, detail="Microclimate dispatch risk config is missing")

    acquisition_report = None
    if refresh_port_local:
        try:
            from kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations import run_fetch_port_local_stations

            acquisition_report = run_fetch_port_local_stations(
                config_path=config_path,
                project_root=MICROCLIMATE_PROJECT_ROOT,
            )
        except Exception as exc:
            logging.exception("port-local data refresh failed")
            acquisition_report = {
                "port_local_data_acquisition_enabled": True,
                "port_local_data_refresh_attempted": True,
                "port_local_data_refresh_success": False,
                "port_local_data_refresh_error": str(exc),
                "port_local_station_files_created": [],
                "fallback_to_existing_files": True,
            }

    try:
        from kaohsiung_microclimate_lstm.src.predict import predict_dispatch_risk_v35
        from kaohsiung_microclimate_lstm.src.preprocess import load_observations

        observations = load_observations(data_path)
        return predict_dispatch_risk_v35(
            fallback_observations=observations,
            config_path=str(config_path),
            project_root=MICROCLIMATE_PROJECT_ROOT,
            target_area=target_area,
            legacy_target_station_id=target_station_id,
            acquisition_report=acquisition_report,
            no_realtime_khwd_mode=no_realtime_khwd_mode,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("dispatch risk prediction failed for target area %s", target_area)
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


@app.post("/admin/fetch-microclimate-sources")
def fetch_microclimate_sources() -> dict:
    return run_microclimate_source_fetch(MICROCLIMATE_PROJECT_ROOT, MICROCLIMATE_CONFIG_PATH)


@app.get("/admin/scheduler-status")
def scheduler_status() -> dict:
    return fetch_scheduler.status()


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


def render_dispatch_risk_demo() -> str:
    return _render_dispatch_risk_demo_v34()


def _render_dispatch_risk_demo_v34() -> str:
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>高雄港微氣候派工風險</title>
  <style>
    :root{
      --bg:#f3f6f5; --panel:#ffffff; --panel-2:#f8faf9;
      --ink:#1e2b31; --ink-soft:#5a6b70; --hairline:#dbe3e0;
      --accent:#b5652e;
      --lvl-normal:#2e7d5b; --lvl-normal-bg:#e3efe8;
      --lvl-watch:#a8792a; --lvl-watch-bg:#f3ead4;
      --lvl-warning:#c06a2b; --lvl-warning-bg:#f5e3d2;
      --lvl-high:#c14b3a; --lvl-high-bg:#f6dcd7;
      --lvl-stop:#a5292a; --lvl-stop-bg:#f4d6d5;
      --lvl-unavailable:#8b969a; --lvl-unavailable-bg:#e9edec;
    }
    @media (prefers-color-scheme: dark){
      :root{
        --bg:#0e1719; --panel:#16211f; --panel-2:#101b19;
        --ink:#e9efee; --ink-soft:#9caeae; --hairline:#28393a;
        --accent:#d98a52;
        --lvl-normal:#5fbf93; --lvl-normal-bg:#16332a;
        --lvl-watch:#d9b463; --lvl-watch-bg:#3a3220;
        --lvl-warning:#e3934f; --lvl-warning-bg:#40291b;
        --lvl-high:#e2756a; --lvl-high-bg:#3f231f;
        --lvl-stop:#ea6b6b; --lvl-stop-bg:#3f1e1e;
        --lvl-unavailable:#7c8a8a; --lvl-unavailable-bg:#20302f;
      }
      pre{ background:#0a1213 !important; }
    }
    *{ box-sizing:border-box; }
    body{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,"Segoe UI","Noto Sans TC",system-ui,sans-serif; line-height:1.5; }
    header{ background:var(--panel); border-bottom:1px solid var(--hairline); }
    .wrap{ width:min(1180px, calc(100% - 32px)); margin:0 auto; }
    .top{ display:flex; justify-content:space-between; gap:16px; align-items:flex-end; padding:18px 0; flex-wrap:wrap; }
    h1,h2{ font-family:Georgia,"Iowan Old Style","Noto Serif TC",serif; text-wrap:balance; margin:0; }
    h1{ font-size:1.6rem; font-weight:600; }
    h2{ font-size:1.05rem; font-weight:600; margin-bottom:10px; }
    .eyebrow{ font-size:0.72rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--accent); font-weight:600; margin-bottom:0.3rem; }
    main{ padding:20px 0 40px; }
    .num{ font-family:ui-monospace,"SF Mono",Consolas,monospace; font-variant-numeric:tabular-nums; }
    button, a.button{ border:0; background:var(--accent); color:#fff; border-radius:6px; min-height:36px; padding:8px 14px; font:inherit; font-weight:600; text-decoration:none; cursor:pointer; }
    button.secondary, a.button.secondary{ background:transparent; color:var(--ink-soft); border:1px solid var(--hairline); }
    button:disabled{ opacity:.6; cursor:wait; }
    input{ min-height:36px; width:160px; border:1px solid var(--hairline); border-radius:6px; padding:7px 9px; font:inherit; background:var(--panel); color:var(--ink); }
    .toolbar{ display:flex; flex-wrap:wrap; align-items:end; gap:10px; margin-bottom:16px; }
    label{ display:grid; gap:4px; color:var(--ink-soft); font-size:13px; }
    .status{ min-height:24px; color:var(--ink-soft); margin-bottom:16px; font-size:0.85rem; }
    .grid{ display:grid; gap:12px; }
    .summary{ grid-template-columns:repeat(4, minmax(0, 1fr)); margin-bottom:16px; }
    .wide{ grid-template-columns:1fr 1fr; margin-top:16px; }
    .panel{ background:var(--panel); border:1px solid var(--hairline); border-radius:8px; padding:14px; }
    .metric-label{ color:var(--ink-soft); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.03em; margin-bottom:6px; }
    .metric-value{ font-family:Georgia,serif; font-size:1.3rem; font-weight:600; overflow-wrap:anywhere; }
    .muted{ color:var(--ink-soft); }
    .small{ font-size:13px; }
    .rows{ display:grid; gap:8px; }
    .row{ display:flex; justify-content:space-between; gap:12px; border-top:1px solid var(--hairline); padding-top:8px; font-size:14px; }
    .row span:first-child{ color:var(--ink-soft); }
    .row span:last-child{ text-align:right; font-weight:600; overflow-wrap:anywhere; font-family:ui-monospace,"SF Mono",Consolas,monospace; }
    .pill{ display:inline-flex; align-items:center; min-height:22px; border-radius:999px; padding:2px 9px; font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.02em; background:var(--lvl-normal-bg); color:var(--lvl-normal); }
    .pill.watch{ background:var(--lvl-watch-bg); color:var(--lvl-watch); }
    .pill.warning{ background:var(--lvl-warning-bg); color:var(--lvl-warning); }
    .pill.high_risk{ background:var(--lvl-high-bg); color:var(--lvl-high); }
    .pill.stop{ background:var(--lvl-stop-bg); color:var(--lvl-stop); }
    .pill.unavailable, .pill.none{ background:var(--lvl-unavailable-bg); color:var(--lvl-unavailable); }
    table{ width:100%; border-collapse:collapse; min-width:720px; }
    th, td{ border-bottom:1px solid var(--hairline); padding:9px 10px; text-align:left; font-size:14px; vertical-align:top; }
    th{ color:var(--ink-soft); background:var(--panel-2); font-weight:600; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.02em; }
    .table-wrap{ overflow-x:auto; border:1px solid var(--hairline); border-radius:8px; background:var(--panel); }
    pre{ margin:0; max-height:360px; overflow:auto; border:1px solid var(--hairline); border-radius:8px; padding:12px; background:#101828; color:#e6edf3; font-size:12px; }

    /* H1-H4 dispatch cards */
    .anchor-strip{ display:grid; grid-template-columns:repeat(4, 1fr); gap:0.9rem; }
    .anchor-card{ background:var(--panel); border:1px solid var(--hairline); border-radius:10px; padding:1.1rem; display:flex; flex-direction:column; gap:0.8rem; border-top:4px solid var(--lvl-normal); }
    .anchor-card.watch{ border-top-color:var(--lvl-watch); }
    .anchor-card.warning{ border-top-color:var(--lvl-warning); }
    .anchor-card.high_risk{ border-top-color:var(--lvl-high); }
    .anchor-card.stop{ border-top-color:var(--lvl-stop); }
    .h-label{ font-size:0.72rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--ink-soft); font-weight:600; }
    .h-time{ font-size:0.76rem; color:var(--ink-soft); margin-top:0.1rem; }
    .action-badge{ padding:0.6rem 0.7rem; border-radius:8px; font-weight:700; font-size:1rem; background:var(--lvl-normal-bg); color:var(--lvl-normal); }
    .anchor-card.watch .action-badge{ background:var(--lvl-watch-bg); color:var(--lvl-watch); }
    .anchor-card.warning .action-badge{ background:var(--lvl-warning-bg); color:var(--lvl-warning); }
    .anchor-card.high_risk .action-badge{ background:var(--lvl-high-bg); color:var(--lvl-high); }
    .anchor-card.stop .action-badge{ background:var(--lvl-stop-bg); color:var(--lvl-stop); }
    .var-row{ display:flex; justify-content:space-between; align-items:center; font-size:0.82rem; padding:0.35rem 0; border-top:1px solid var(--hairline); }
    .var-row .var-name{ color:var(--ink-soft); }
    .var-row .var-val{ display:flex; align-items:center; gap:0.4rem; font-family:ui-monospace,"SF Mono",Consolas,monospace; }
    .trigger-note{ font-size:0.74rem; color:var(--ink-soft); background:var(--panel-2); border-radius:6px; padding:0.5rem 0.6rem; }
    .trigger-note strong{ color:var(--ink); }

    @media (max-width: 900px) { .summary, .wide { grid-template-columns:1fr; } .top { align-items:flex-start; flex-direction:column; } .anchor-strip{ grid-template-columns:1fr 1fr; } }
    @media (max-width: 560px) { .anchor-strip{ grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <div class="wrap top">
      <div>
        <div class="eyebrow">高雄港・派工決策主控台</div>
        <h1>高雄港微氣候派工風險</h1>
        <div class="muted small">v3.5 系統盤點、資料來源、測站、資料集、模型摘要、station_priority_summary</div>
      </div>
      <nav>
        <a class="button secondary" href="/api/v1/dispatch/risk?target_area=KHH" target="_blank">JSON 原始資料</a>
        <a class="button secondary" href="/api/v1/dispatch/system-audit?target_area=KHH" target="_blank">系統盤點</a>
        <a class="button secondary" href="/api/v1/dispatch/model-status?target_area=KHH" target="_blank">模型狀態</a>
        <a class="button secondary" href="/docs" target="_blank">API 文件</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <div class="toolbar">
      <button id="fetch-latest" class="secondary" type="button">抓取最新資料</button>
      <label>目標港區<input id="target-area" value="KHH"></label>
      <label><input id="no-khwd" type="checkbox" style="width:auto; min-height:auto"> 模擬 KHWD 不可用</label>
      <button id="refresh" type="button">更新</button>
    </div>
    <div id="status" class="status">載入中...</div>
    <section id="overview" class="grid summary"></section>

    <section class="panel" style="margin-bottom:16px;">
      <h2>H1-H4 派工建議</h2>
      <div id="anchor-strip" class="anchor-strip"></div>
    </section>
    <section class="panel" style="margin-bottom:16px;">
      <h2>CWA +3h/+6h 官方預報</h2>
      <div id="cwa-window-strip" class="anchor-strip"></div>
    </section>

    <section class="grid wide">
      <div class="panel">
        <h2>模型狀態</h2>
        <div id="model-status" class="rows"></div>
      </div>
      <div class="panel">
        <h2>目前測站使用</h2>
        <div id="station-usage" class="rows"></div>
      </div>
    </section>
    <section class="panel">
      <h2>系統盤點摘要</h2>
      <div id="audit-cards" class="grid summary"></div>
    </section>
    <section class="panel">
      <h2>資料來源盤點</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>來源</th><th>類型</th><th>角色</th><th>用途</th><th>模型輸入</th><th>目前使用</th><th>狀態</th></tr></thead>
          <tbody id="data-source-rows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>測站角色表</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>測站代碼</th><th>名稱</th><th>群組</th><th>角色</th><th>資料類型</th><th>使用中</th><th>核心測站</th><th>備援</th></tr></thead>
          <tbody id="station-rows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel" style="margin-top:16px;">
      <h2>資料期間</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>資料集</th><th>角色</th><th>起始</th><th>結束</th><th>天數</th><th>筆數</th><th>狀態</th></tr></thead>
          <tbody id="dataset-rows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel" style="margin-top:16px;">
      <h2>模型指標</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>模型</th><th>狀態</th><th>風速 H1 MAE</th><th>陣風 H1 MAE</th><th>降雨 Brier</th><th>已核准</th></tr></thead>
          <tbody id="metric-rows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>原始回傳資料</h2>
      <pre id="raw-json">{}</pre>
    </section>
  </main>
  <script>
    const $ = id => document.getElementById(id);
    const text = (value, fallback = "-") => value === null || value === undefined || value === "" ? fallback : String(value);
    const percent = value => value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : `${Math.round(Number(value) * 100)}%`;
    const number = value => value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(1);
    const row = (label, value) => `<div class="row"><span>${label}</span><span>${value}</span></div>`;
    const metric = (label, value, sub = "") => `<div class="panel"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="muted small">${sub}</div></div>`;
    const levelClass = level => (text(level, "normal")).toLowerCase();
    const levelLabels = { normal: "正常", watch: "注意", warning: "警戒", high_risk: "高風險", stop: "停止", unavailable: "無法取得", none: "無" };
    const pill = level => `<span class="pill ${levelClass(level)}">${levelLabels[levelClass(level)] || text(level)}</span>`;
    const actionLabels = { normal_dispatch: "正常派工", observe_only: "觀察", monitor: "監控", restrict_sensitive_tasks: "限制敏感作業", delay_high_risk_tasks: "延後高風險作業", suspend_exposed_tasks: "暫停暴露作業" };
    const triggerLabels = { wind_gust: "陣風", wind_speed: "風速", rain_probability: "降雨機率", visibility: "能見度", tide: "潮位", none: "無" };
    const statusLabels = { available: "可用", not_available: "不可用", unknown: "未知", disabled: "已停用", fallback_available: "備援可用", degraded: "降級", ok: "正常" };
    const statusText = value => statusLabels[value] || text(value);

    function renderAudit(audit) {
      const cards = audit.dashboard_cards || [];
      $("audit-cards").innerHTML = cards.map(card => metric(card.title, text(card.value), text(card.description))).join("");
      const tables = audit.dashboard_tables || {};
      $("data-source-rows").innerHTML = (tables.data_sources || []).map(item => `
        <tr>
          <td>${text(item.source_id)}</td><td>${text(item.source_type)}</td><td>${text(item.role)}</td>
          <td>${(item.used_for || []).join(", ")}</td><td>${item.used_as_model_input ? "是" : "否"}</td>
          <td>${item.used_for_current_prediction ? "是" : "否"}</td><td>${statusText(item.status)}</td>
        </tr>`).join("");
      $("dataset-rows").innerHTML = (tables.dataset_durations || []).map(item => `
        <tr>
          <td>${text(item.dataset_id)}</td><td>${text(item.role)}</td><td>${text(item.time_start, "無資料")}</td>
          <td>${text(item.time_end, "無資料")}</td><td>${text(item.duration_days, "無資料")}</td>
          <td>${text(item.total_rows, "無資料")}</td><td>${statusText(item.status)}</td>
        </tr>`).join("");
      $("metric-rows").innerHTML = (tables.model_metrics || []).map(item => `
        <tr>
          <td>${text(item.model_id)}</td><td>${statusText(item.activation_status || item.metrics_status)}</td>
          <td>${text(item.metrics?.wind_speed?.H1?.mae_mps, "無資料")}</td>
          <td>${text(item.metrics?.wind_gust?.H1?.mae_mps, "無資料")}</td>
          <td>${text(item.metrics?.rain_probability?.H1?.brier_score, "無資料")}</td>
          <td>${item.accepted ? "是" : "否"}</td>
        </tr>`).join("");
    }

    function renderAnchorCards(anchors) {
      $("anchor-strip").innerHTML = anchors.map(anchor => {
        const level = levelClass(anchor.dispatch_risk_level);
        const threeHour = anchor.rain?.three_hour_accumulation_estimate;
        const amount = anchor.rain?.predicted_amount_mm;
        const trigger = anchor.risk_trigger_detail || {};
        const actionLabel = anchor.dispatch_action?.action_label || actionLabels[anchor.dispatch_action_level] || text(anchor.dispatch_action_level);
        const triggerText = trigger.primary_trigger && trigger.primary_trigger !== "none"
          ? `<strong>觸發來源：${triggerLabels[trigger.primary_trigger] || text(trigger.primary_trigger)}</strong>（${levelLabels[levelClass(trigger.primary_trigger_level)] || text(trigger.primary_trigger_level)}）${trigger.is_low_reliability_trigger ? "，可靠度較低，建議觀察" : ""}`
          : "五項風險皆為正常，無觸發項目。";
        return `
        <div class="anchor-card ${level}">
          <div>
            <div class="h-label">${text(anchor.label)} · +${text(anchor.offset_minutes)} 分鐘</div>
            <div class="h-time num">${text(anchor.timestamp, "")}</div>
          </div>
          <div class="action-badge">${actionLabel}</div>
          <div class="var-row"><span class="var-name">降雨機率</span><span class="var-val">${percent(anchor.rain?.final_probability)} ${pill(anchor.rain?.level)}</span></div>
          <div class="var-row"><span class="var-name">降雨量</span><span class="var-val">${amount === null || amount === undefined ? "-" : `${number(amount)} mm`} ${pill(anchor.rain?.amount_level)}</span></div>
          <div class="var-row"><span class="var-name">3小時累積估計</span><span class="var-val">${threeHour ? `${number(threeHour.predicted_amount_mm)} mm（推算）` : "-"}</span></div>
          <div class="var-row"><span class="var-name">風速</span><span class="var-val">${number(anchor.wind_speed?.predicted_mps)} m/s ${pill(anchor.wind_speed?.operation_level)}</span></div>
          <div class="var-row"><span class="var-name">陣風</span><span class="var-val">${number(anchor.wind_gust?.predicted_mps)} m/s ${pill(anchor.wind_gust?.operation_level)}</span></div>
          <div class="trigger-note">${triggerText}</div>
        </div>`;
      }).join("");
    }

    function renderCwaWindows(extended) {
      const holder = $("cwa-window-strip");
      if (!extended || !extended.available) {
        holder.innerHTML = `<div class="trigger-note">CWA 官方 +3h/+6h 預報目前不可用：${text(extended?.reason, "無資料")}</div>`;
        return;
      }
      holder.innerHTML = (extended.windows || []).map(item => `
        <div class="anchor-card ${levelClass(item.wind_speed?.operation_level || item.rain_probability?.level)}">
          <div>
            <div class="h-label">${text(item.window)} · CWA 官方預報</div>
            <div class="h-time num">${text(item.data_id)}</div>
          </div>
          <div class="var-row"><span class="var-name">風速</span><span class="var-val">${item.wind_speed?.available ? `${number(item.wind_speed.value_mps)} m/s` : "-"} ${pill(item.wind_speed?.operation_level || "unavailable")}</span></div>
          <div class="var-row"><span class="var-name">降雨機率</span><span class="var-val">${item.rain_probability?.available ? percent(item.rain_probability.value) : "-"} ${pill(item.rain_probability?.level || "unavailable")}</span></div>
          <div class="var-row"><span class="var-name">陣風</span><span class="var-val">${pill("unavailable")}</span></div>
          <div class="var-row"><span class="var-name">能見度</span><span class="var-val">${pill("unavailable")}</span></div>
        </div>`).join("");
    }

    function render(payload, audit) {
      const trace = payload.trace || {};
      const training = payload.model_training_status || {};
      const models = training.available_models || {};
      const nearby = models.nearby_cwa_historical_model || {};
      const port = models.port_local_model || {};
      const usage = payload.current_station_usage || {};
      const anchors = payload.forecast_anchors || [];
      $("overview").innerHTML = [
        metric("模型版本", text(payload.model_version), text(payload.generated_at)),
        metric("預測模式", text(payload.prediction_mode), text(trace.selection_case_id)),
        metric("時間基準", text(payload.anchor_time_source), `誤差 ${text(payload.anchor_time_staleness_minutes, "?")} 分鐘`),
        metric("467441 備援", trace.fallback_to_467441 ? "是" : "否", `核心測站=${trace["467441_used_as_core_station"] ? "是" : "否"}`)
      ].join("");
      $("model-status").innerHTML = [
        row("港區在地模型", `${port.trained ? "已訓練" : "未訓練"} / ${port.accepted ? "已核准" : "未核准"}`),
        row("鄰近氣象站模型", `${nearby.trained ? "已訓練" : "未訓練"} / ${nearby.accepted ? "已核准" : "未核准"}`),
        row("模型註冊表已載入", trace.model_registry_loaded ? "是" : "否"),
        row("模型清單已檢查", trace.model_manifest_checked ? "是" : "否"),
        row("降雨機率已保留", trace.rain_probability_preserved ? "是" : "否")
      ].join("");
      $("station-usage").innerHTML = [
        row("風速來源", text(usage.active_wind_source)),
        row("陣風來源", text(usage.active_gust_source)),
        row("降雨來源", text(usage.active_rain_source)),
        row("港區測站使用", (usage.port_local_station_ids_used || []).join(", ") || "-"),
        row("鄰近測站使用", (usage.nearby_cwa_station_ids_used_for_current_prediction || []).join(", ") || "-"),
        row("基準測站使用", usage.baseline_station_used_for_current_prediction ? "是" : "否")
      ].join("");
      $("station-rows").innerHTML = (payload.station_display_rows || []).map(item => `
        <tr>
          <td>${text(item.station_id)}</td><td>${text(item.station_name)}</td><td>${text(item.station_group)}</td><td>${text(item.role)}</td>
          <td>${(item.data_type || []).join(", ")}</td><td>${item.used_for_current_prediction ? "是" : "否"}</td>
          <td>${item.is_port_local_core ? "是" : "否"}</td><td>${item.is_fallback_reference ? "是" : "否"}</td>
        </tr>`).join("");
      renderAnchorCards(anchors);
      renderCwaWindows(payload.extended_forecast_windows);
      $("raw-json").textContent = JSON.stringify(payload, null, 2);
      $("status").textContent = `已更新：${text(payload.generated_at)}`;
      if (audit) renderAudit(audit);
    }

    async function loadRisk() {
      const target = $("target-area").value.trim() || "KHH";
      const params = new URLSearchParams({target_area: target});
      if ($("no-khwd").checked) params.set("no_realtime_khwd_mode", "true");
      $("refresh").disabled = true;
      $("status").textContent = "載入中...";
      try {
        const [riskResponse, auditResponse] = await Promise.all([
          fetch(`/api/v1/dispatch/risk?${params.toString()}`),
          fetch(`/api/v1/dispatch/system-audit?target_area=${encodeURIComponent(target)}`)
        ]);
        const payload = await riskResponse.json();
        const audit = await auditResponse.json();
        if (!riskResponse.ok) throw new Error(payload.detail || `HTTP ${riskResponse.status}`);
        if (!auditResponse.ok) throw new Error(audit.detail || `HTTP ${auditResponse.status}`);
        render(payload, audit);
      } catch (error) {
        $("status").textContent = `載入失敗：${error.message}`;
      } finally {
        $("refresh").disabled = false;
      }
    }

    async function fetchLatestSources() {
      $("fetch-latest").disabled = true;
      $("refresh").disabled = true;
      $("status").textContent = "正在抓取最新資料...";
      try {
        const response = await fetch("/admin/fetch-microclimate-sources", { method: "POST" });
        const payload = await response.json();
        if (!response.ok || payload.error) throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
        const ok = payload.success_count ?? 0;
        const total = payload.task_count ?? 0;
        $("status").textContent = `抓取完成：${ok}/${total}，正在更新派工預測...`;
        await loadRisk();
      } catch (error) {
        $("status").textContent = `抓取失敗：${error.message}`;
      } finally {
        $("fetch-latest").disabled = false;
        $("refresh").disabled = false;
      }
    }

    $("refresh").addEventListener("click", loadRisk);
    $("fetch-latest").addEventListener("click", fetchLatestSources);
    $("target-area").addEventListener("keydown", event => { if (event.key === "Enter") loadRisk(); });
    $("no-khwd").addEventListener("change", loadRisk);
    loadRisk();
  </script>
</body>
</html>"""




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
