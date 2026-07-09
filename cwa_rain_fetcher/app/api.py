import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.config import settings
from app.cwa_client import CWAClient
from app.storage import RainStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

async def run_sync_internal() -> dict[str, Any]:
    """Helper function to execute synchronization with configured filters."""
    if not settings.cwa_api_key:
        raise ValueError("CWA_API_KEY is not configured in .env")
        
    client = CWAClient(settings.cwa_api_key, verify_ssl=settings.cwa_verify_ssl)
    
    # Fetch forecasts filtered by configured location names (defaults to Kaohsiung City)
    forecasts = await client.get_forecasts(target_locations=settings.target_forecast_locations)
    fc_saved = storage.save_forecasts(forecasts)
    
    # Fetch observations filtered by configured station IDs (defaults to Kaohsiung Port area stations)
    observations = await client.get_observations(target_stations=settings.target_station_ids)
    obs_saved = storage.save_observations(observations)
    
    # Fetch 1-hour QPF grid prediction nearest to the target port coordinates
    qpf = await client.get_qpf(lat=settings.target_latitude, lon=settings.target_longitude)
    qpf_saved = storage.save_qpf(qpf) if qpf else 0
    
    return {
        "forecasts_fetched": len(forecasts),
        "forecasts_upserted": fc_saved,
        "observations_fetched": len(observations),
        "observations_upserted": obs_saved,
        "qpf_fetched": 1 if qpf else 0,
        "qpf_upserted": qpf_saved
    }

async def auto_sync_loop():
    """Background task loop for periodic CWA data synchronization."""
    # Delay initial fetch slightly to let server start up
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("Auto-sync: starting scheduled CWA rain data collection...")
            res = await run_sync_internal()
            logger.info("Auto-sync completed. Results: %s", res)
        except Exception as exc:
            logger.error("Auto-sync error in background task: %s", exc)
            
        logger.info("Auto-sync: sleeping for %d seconds...", settings.auto_sync_interval_seconds)
        await asyncio.sleep(settings.auto_sync_interval_seconds)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background worker task if enabled
    worker_task = None
    if settings.auto_sync_enabled:
        logger.info("Starting background auto-sync worker...")
        worker_task = asyncio.create_task(auto_sync_loop())
    
    yield
    
    # Shutdown: Cancel background worker task
    if worker_task:
        logger.info("Stopping background auto-sync worker...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="CWA Rain Fetcher API", version="1.0.0", lifespan=lifespan)
storage = RainStorage(settings.database_path)

@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "api_configured": bool(settings.cwa_api_key),
        "database": str(settings.database_path.name),
        "auto_sync_enabled": settings.auto_sync_enabled,
        "auto_sync_interval_seconds": settings.auto_sync_interval_seconds
    }

@app.post("/api/sync")
async def sync_data() -> dict[str, Any]:
    """Manually fetch and sync data from CWA."""
    try:
        results = await run_sync_internal()
        return {
            "success": True,
            **results
        }
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.exception("Synchronization failed")
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")

@app.get("/api/rain/forecast")
def get_forecast(location: str | None = Query(None)) -> dict[str, Any]:
    """Retrieve forecast PoP from local DB."""
    if location:
        data = storage.get_all_forecasts_for_location(location)
    else:
        data = storage.get_latest_forecasts()
    return {"data": data}

@app.get("/api/rain/actual")
def get_actual(county: str | None = Query(None)) -> dict[str, Any]:
    """Retrieve actual rainfall observations from local DB."""
    data = storage.get_latest_observations(county=county)
    return {"data": data}

@app.get("/api/rain/qpf")
def get_qpf(
    lat: float = Query(None),
    lon: float = Query(None),
    limit: int = Query(24)
) -> dict[str, Any]:
    """Retrieve 1-hour QPF prediction history for coordinates from local DB."""
    latitude = lat if lat is not None else settings.target_latitude
    longitude = lon if lon is not None else settings.target_longitude
    data = storage.get_latest_qpf(latitude=latitude, longitude=longitude, limit=limit)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "data": data
    }

@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    """Retrieve database synchronization statistics."""
    return storage.get_db_stats()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Render a premium CWA Rain Dashboard."""
    return render_dashboard()

def render_dashboard() -> str:
    return """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CWA 降雨量與降雨機率監控面板</title>
  <!-- Google Fonts Outfit & Noto Sans TC -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+TC:wght@300;400;500;700&display=swap" rel="stylesheet">
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg-gradient: linear-gradient(135deg, #0f0c1b 0%, #15102a 50%, #090613 100%);
      --glass-bg: rgba(26, 21, 44, 0.45);
      --glass-border: rgba(255, 255, 255, 0.08);
      --glass-glow: rgba(99, 102, 241, 0.15);
      
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.4);
      --accent-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
      
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --info: #06b6d4;
    }
    
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    
    body {
      background: var(--bg-gradient);
      color: var(--text);
      font-family: 'Outfit', 'Noto Sans TC', sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
      padding: 24px 16px;
    }
    
    .container {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    
    /* Header Section */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px;
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    
    .logo-area h1 {
      font-size: 24px;
      font-weight: 700;
      background: var(--accent-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }
    
    .logo-area p {
      font-size: 13px;
      color: var(--text-muted);
    }
    
    .action-area {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    
    /* Buttons */
    .btn {
      background: var(--accent-gradient);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 10px 20px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }
    
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
    }
    
    .btn:active {
      transform: translateY(0);
    }
    
    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }
    
    /* Stats Bar */
    .stats-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }
    
    .stat-card {
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      padding: 18px;
      backdrop-filter: blur(12px);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
      transition: border 0.3s;
    }
    
    .stat-card:hover {
      border-color: rgba(99, 102, 241, 0.3);
    }
    
    .stat-label {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    
    .stat-val {
      font-size: 24px;
      font-weight: 700;
      color: #fff;
    }
    
    .stat-sub {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 4px;
    }
    
    /* Main Dashboard Grid */
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 20px;
    }
    
    .panel {
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      padding-bottom: 12px;
    }
    
    .panel-title {
      font-size: 18px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .panel-title::before {
      content: '';
      display: inline-block;
      width: 4px;
      height: 18px;
      background: var(--accent);
      border-radius: 2px;
    }
    
    /* Custom Select */
    select {
      background: #18142c;
      color: var(--text);
      border: 1px solid var(--glass-border);
      border-radius: 8px;
      padding: 6px 12px;
      font-family: inherit;
      font-size: 14px;
      cursor: pointer;
      outline: none;
    }
    
    select:focus {
      border-color: var(--accent);
    }
    
    /* Tables styling */
    .table-container {
      overflow-x: auto;
      max-height: 400px;
    }
    
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }
    
    th, td {
      padding: 12px 14px;
      font-size: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    
    th {
      font-weight: 600;
      color: var(--text-muted);
      background: rgba(0, 0, 0, 0.15);
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(12px);
    }
    
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 11px;
      font-weight: 700;
    }
    
    .badge-pop-high { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
    .badge-pop-med { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
    .badge-pop-low { background: rgba(16, 185, 129, 0.15); color: var(--success); }
    
    /* Rain alert colors */
    .rainy-cell {
      font-weight: 600;
      color: #38bdf8;
    }
    
    .spinner {
      width: 18px;
      height: 18px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      border-top-color: #fff;
      animation: spin 0.8s linear infinite;
      display: none;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      display: inline-block;
      box-shadow: 0 0 8px var(--success);
    }
    
    .status-dot.syncing {
      background: var(--warning);
      box-shadow: 0 0 8px var(--warning);
      animation: pulse 1s infinite alternate;
    }
    
    @keyframes pulse {
      from { opacity: 0.6; }
      to { opacity: 1; }
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-area">
        <h1>CWA 雨量與降雨機率監控</h1>
        <p>提供降雨機率預報 (F-C0032-001) 與自動雨量觀測實測 (O-A0002-001) 統計</p>
      </div>
      <div class="action-area">
        <span id="sync-status" class="small muted"><span class="status-dot"></span> 系統已就緒</span>
        <button id="sync-btn" class="btn">
          <div id="sync-spinner" class="spinner"></div>
          <span id="sync-btn-text">立即同步數據</span>
        </button>
      </div>
    </header>
    
    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-label">預報縣市</div>
        <div id="stat-forecast-count" class="stat-val">-</div>
        <div id="stat-forecast-sync" class="stat-sub">未同步</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">觀測站數 (目標)</div>
        <div id="stat-obs-count" class="stat-val">-</div>
        <div id="stat-obs-sync" class="stat-sub">未同步</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">高雄港最新 QPF 預測</div>
        <div id="stat-qpf-latest" class="stat-val">- mm</div>
        <div id="stat-qpf-sync" class="stat-sub">未同步</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累積雨量最大站</div>
        <div id="stat-max-rain-name" class="stat-val">-</div>
        <div id="stat-max-rain-val" class="stat-sub">- mm</div>
      </div>
    </div>
    
    <!-- Dashboard Grid -->
    <div class="dashboard-grid">
      <!-- Forecast Panel -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">縣市降雨機率預報 (36小時)</div>
          <select id="location-selector">
            <option value="高雄市">高雄市</option>
            <option value="臺北市">臺北市</option>
            <option value="新北市">新北市</option>
            <option value="臺中市">臺中市</option>
            <option value="臺南市">臺南市</option>
            <option value="桃園市">桃園市</option>
            <option value="基隆市">基隆市</option>
            <option value="新竹市">新竹市</option>
            <option value="嘉義市">嘉義市</option>
            <option value="屏東縣">屏東縣</option>
            <option value="花蓮縣">花蓮縣</option>
            <option value="宜蘭縣">宜蘭縣</option>
          </select>
        </div>
        <div style="position: relative; height: 260px;">
          <canvas id="forecastChart"></canvas>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>時段</th>
                <th>降雨機率</th>
                <th>天氣現象</th>
              </tr>
            </thead>
            <tbody id="forecast-table-body">
              <tr><td colspan="3" style="text-align:center;">載入中...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- QPF Panel -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">高雄港 1小時定量降雨預測 (QPF 趨勢)</div>
          <span style="font-size:12px;color:var(--text-muted); padding: 4px 10px; border: 1px solid var(--glass-border); border-radius: 8px; background: rgba(0,0,0,0.15);">座標: <span id="qpf-coords">-</span></span>
        </div>
        <div style="position: relative; height: 260px;">
          <canvas id="qpfChart"></canvas>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>預估時段</th>
                <th>預估雨量</th>
                <th>資料更新時間</th>
              </tr>
            </thead>
            <tbody id="qpf-table-body">
              <tr><td colspan="3" style="text-align:center;">載入中...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      
      <!-- Observation Panel -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">實時降雨量觀測 (依累積雨量排序)</div>
          <select id="county-selector">
            <option value="">全部縣市</option>
            <option value="高雄市">高雄市</option>
            <option value="臺北市">臺北市</option>
            <option value="新北市">新北市</option>
            <option value="臺中市">臺中市</option>
            <option value="臺南市">臺南市</option>
            <option value="花蓮縣">花蓮縣</option>
            <option value="屏東縣">屏東縣</option>
          </select>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>測站</th>
                <th>地區</th>
                <th>1小時雨量</th>
                <th>24小時累積</th>
                <th>觀測時間</th>
              </tr>
            </thead>
            <tbody id="obs-table-body">
              <tr><td colspan="5" style="text-align:center;">載入中...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
  
  <script>
    const $ = id => document.getElementById(id);
    let forecastChart = null;
    let qpfChart = null;
    
    // Format ISO Datetime to friendly string
    function formatTime(isoStr) {
      if(!isoStr) return "-";
      const d = new Date(isoStr);
      return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }
    
    // Get badge based on PoP
    function getPopBadge(pop) {
      if (pop >= 60) return `<span class="badge badge-pop-high">${pop}% 高</span>`;
      if (pop >= 30) return `<span class="badge badge-pop-med">${pop}% 中</span>`;
      return `<span class="badge badge-pop-low">${pop}% 低</span>`;
    }
    
    // Format rain cell color
    function getRainCell(val) {
      if (val === null || val === undefined) return '<span class="muted">-</span>';
      if (val > 0) return `<span class="rainy-cell">${val.toFixed(1)} mm</span>`;
      return '<span class="muted">0.0 mm</span>';
    }
    
    // Init Forecast Chart
    function initChart(labels, data) {
      const ctx = $('forecastChart').getContext('2d');
      
      if(forecastChart) {
        forecastChart.destroy();
      }
      
      forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '降雨機率 (%)',
            data: data,
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            borderWidth: 3,
            tension: 0.3,
            fill: true,
            pointBackgroundColor: '#a855f7',
            pointRadius: 5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            y: {
              min: 0,
              max: 100,
              ticks: { color: '#9ca3af' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            },
            x: {
              ticks: { color: '#9ca3af' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            }
          }
        }
      });
    }

    // Init QPF Chart
    function initQpfChart(labels, data) {
      const ctx = $('qpfChart').getContext('2d');
      
      if(qpfChart) {
        qpfChart.destroy();
      }
      
      qpfChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '預估雨量 (mm/h)',
            data: data,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            borderWidth: 3,
            tension: 0.3,
            fill: true,
            pointBackgroundColor: '#06b6d4',
            pointRadius: 5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            y: {
              min: 0,
              ticks: { color: '#9ca3af' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            },
            x: {
              ticks: { color: '#9ca3af' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            }
          }
        }
      });
    }
    
    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        
        $('stat-forecast-count').textContent = stats.forecast_total_rows > 0 ? "已同步" : "無資料";
        $('stat-forecast-sync').textContent = stats.last_forecast_sync ? `同步時間: ${formatTime(stats.last_forecast_sync)}` : "未同步";
        
        $('stat-obs-count').textContent = stats.observation_total_rows > 0 ? stats.observation_total_rows : "0";
        $('stat-obs-sync').textContent = stats.last_observation_sync ? `同步時間: ${formatTime(stats.last_observation_sync)}` : "未同步";
      } catch (err) {
        console.error("Error loading stats", err);
      }
    }
    
    async function loadForecast() {
      const location = $('location-selector').value;
      try {
        const res = await fetch(`/api/rain/forecast?location=${encodeURIComponent(location)}`);
        const result = await res.json();
        const forecasts = result.data || [];
        
        if (forecasts.length === 0) {
          $('forecast-table-body').innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">無預測資料，請點擊同步按鈕</td></tr>';
          initChart([], []);
          return;
        }
        
        // Build table
        $('forecast-table-body').innerHTML = forecasts.map(item => `
          <tr>
            <td>${formatTime(item.start_time)} ~ ${formatTime(item.end_time)}</td>
            <td>${getPopBadge(item.pop)}</td>
            <td>${item.wx_phenomenon}</td>
          </tr>
        `).join('');
        
        // Build chart
        const labels = forecasts.map(item => {
          const start = new Date(item.start_time);
          return `${start.getMonth()+1}/${start.getDate()} ${start.getHours()}h`;
        });
        const data = forecasts.map(item => item.pop);
        initChart(labels, data);
        
      } catch (err) {
        console.error("Error loading forecast", err);
        $('forecast-table-body').innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--danger);">載入預報失敗</td></tr>';
      }
    }

    async function loadQpf() {
      try {
        const res = await fetch('/api/rain/qpf');
        const result = await res.json();
        const qpfData = result.data || [];
        
        $('qpf-coords').textContent = `${result.latitude}, ${result.longitude}`;
        
        if (qpfData.length === 0) {
          $('qpf-table-body').innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">無定量降雨預測資料，請點擊同步按鈕</td></tr>';
          initQpfChart([], []);
          $('stat-qpf-latest').textContent = "0.0 mm";
          $('stat-qpf-sync').textContent = "未同步";
          return;
        }
        
        // Latest prediction
        const latest = qpfData[qpfData.length - 1];
        $('stat-qpf-latest').textContent = `${latest.qpf_1hr_mm.toFixed(1)} mm`;
        $('stat-qpf-sync').textContent = latest.obs_time ? `預估時間: ${formatTime(latest.obs_time)}` : "未同步";
        
        // Build table
        const displayData = [...qpfData].reverse();
        $('qpf-table-body').innerHTML = displayData.map(item => {
          const start = new Date(item.obs_time);
          const end = new Date(start.getTime() + 60*60*1000);
          return `
            <tr>
              <td>${formatTime(start.toISOString())} ~ ${formatTime(end.toISOString())}</td>
              <td class="rainy-cell">${item.qpf_1hr_mm.toFixed(1)} mm</td>
              <td>${formatTime(item.fetched_at)}</td>
            </tr>
          `;
        }).join('');
        
        // Build chart
        const labels = qpfData.map(item => {
          const t = new Date(item.obs_time);
          return `${t.getMonth()+1}/${t.getDate()} ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
        });
        const data = qpfData.map(item => item.qpf_1hr_mm);
        initQpfChart(labels, data);
        
      } catch (err) {
        console.error("Error loading QPF", err);
        $('qpf-table-body').innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--danger);">載入預測失敗</td></tr>';
      }
    }
    
    async function loadObservations() {
      const county = $('county-selector').value;
      try {
        const res = await fetch(`/api/rain/actual?county=${encodeURIComponent(county)}`);
        const result = await res.json();
        const obs = result.data || [];
        
        if (obs.length === 0) {
          $('obs-table-body').innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">無實測觀測資料，請點擊同步按鈕</td></tr>';
          return;
        }
        
        // Update stats bar max rain
        const maxRainStation = obs[0]; // Already sorted by precipitation_24hr DESC
        if (maxRainStation && maxRainStation.precipitation_24hr > 0) {
          $('stat-max-rain-name').textContent = maxRainStation.station_name;
          $('stat-max-rain-val').textContent = `${maxRainStation.precipitation_24hr.toFixed(1)} mm (${maxRainStation.county})`;
        } else if (obs.length > 0) {
          $('stat-max-rain-name').textContent = "今日無雨";
          $('stat-max-rain-val').textContent = "0.0 mm";
        }
        
        $('obs-table-body').innerHTML = obs.map(item => `
          <tr>
            <td><strong>${item.station_name}</strong><br><span style="font-size:11px;color:var(--text-muted);">${item.station_id}</span></td>
            <td>${item.county || ''} ${item.town || ''}</td>
            <td>${getRainCell(item.precipitation_1hr)}</td>
            <td>${getRainCell(item.precipitation_24hr)}</td>
            <td>${formatTime(item.obs_time)}</td>
          </tr>
        `).join('');
      } catch (err) {
        console.error("Error loading observations", err);
        $('obs-table-body').innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--danger);">載入觀測失敗</td></tr>';
      }
    }
    
    // Sync Button click event
    $('sync-btn').addEventListener('click', async () => {
      const btn = $('sync-btn');
      const spinner = $('sync-spinner');
      const text = $('sync-btn-text');
      const status = $('sync-status');
      
      btn.disabled = true;
      spinner.style.display = 'block';
      text.textContent = '同步中...';
      status.innerHTML = '<span class="status-dot syncing"></span> 正在與 CWA 伺服器同步中';
      
      try {
        const res = await fetch('/api/sync', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
          status.innerHTML = '<span class="status-dot"></span> 同步完成';
          setTimeout(() => {
            status.innerHTML = '<span class="status-dot"></span> 系統已就緒';
          }, 3000);
        } else {
          status.innerHTML = '<span class="status-dot" style="background:var(--danger);box-shadow:0 0 8px var(--danger);"></span> 同步失敗';
        }
      } catch (err) {
        console.error("Sync error", err);
        status.innerHTML = '<span class="status-dot" style="background:var(--danger);box-shadow:0 0 8px var(--danger);"></span> 連線錯誤';
      } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        text.textContent = '立即同步數據';
        
        // Refresh dashboard
        await loadStats();
        await loadForecast();
        await loadQpf();
        await loadObservations();
      }
    });
    
    // Dropdown change listeners
    $('location-selector').addEventListener('change', loadForecast);
    $('county-selector').addEventListener('change', loadObservations);
    
    // Initial Load
    (async () => {
      await loadStats();
      await loadForecast();
      await loadQpf();
      await loadObservations();
    })();
  </script>
</body>
</html>
"""
