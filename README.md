# Kaohsiung Port Microclimate Prediction System

This repository implements the Kaohsiung Port microclimate and dispatch-risk workflow. The current implementation priority is `高雄港微氣候預測_專案規格書_v1.3.md`; the earlier v2.0 chapter audit is retained as implementation history.

## System Goals

- Predict short-term microclimate anchors at 30, 60, 90, and 120 minutes.
- Support dispatch-risk decisions from wind speed, gusts, precipitation, tide level, and visibility.
- Prefer port-local observations when available, and make fallback behavior explicit.
- Keep data quality, model selection, station usage, and system audit outputs inspectable.

## Architecture

The implementation follows the v1.3/v2.0 layered architecture:

1. Data collection: TWPort, CWA Open Data, CWA marine observations, CODiS historical rainfall, tide/wave observations.
2. Data preprocessing and quality control: station normalization, stale-data checks, historical dataset readiness, missing-value handling.
3. Feature engineering: time-series windows, station-priority features, port-local wind aggregation, nearby CWA aggregation, rain probability priors.
4. Model training and evaluation: LSTM baselines, tree-based port-local models, nearby CWA historical models, model registry, evaluation metrics.
5. Prediction and dispatch risk: deterministic model selection, post-processing, risk-level mapping, action-level mapping.
6. API and reporting: FastAPI endpoints, dashboard payloads, system audit reports, CLI utilities.

## Main API Endpoints

Run the API:

```powershell
uvicorn app.api:app --reload
```

Stable endpoints:

```text
GET /
GET /dispatch-risk-demo
GET /health
GET /docs
GET /api/v1/schema
GET /api/v1/system/info
GET /api/v1/system/requirements
GET /api/v1/system/data-spec
GET /api/v1/system/feature-spec
GET /api/v1/system/model-spec
GET /api/v1/system/evaluation-spec
GET /api/v1/system/api-spec
GET /api/v1/system/deployment-spec
GET /api/v1/system/testing-spec
GET /api/v1/system/schedule-spec
GET /api/v1/system/appendix-spec
GET /api/v1/microclimate/current
GET /api/v1/microclimate/forecast?minutes=90
GET /api/v1/dispatch/risk?target_area=KHH
GET /api/v1/dispatch/model-status?target_area=KHH
GET /api/v1/dispatch/station-usage?target_area=KHH
GET /api/v1/dispatch/system-audit?target_area=KHH
POST /admin/fetch-microclimate-sources
GET /admin/scheduler-status
```

## Project Layout

```text
app/                            FastAPI app, collectors, storage, API contracts
kaohsiung_microclimate_lstm/    Modeling, training, prediction, risk, and audit pipeline
tests/                          Main project tests
docs/                           Contracts, operations notes, and implementation audit files
```

Raw training data (`kaohsiung_microclimate_lstm/data/raw/historical_weather/`) and processed
training-pipeline intermediates (`kaohsiung_microclimate_lstm/data/processed/`) are not tracked
in git — they are large and can be regenerated from public sources. Trained model artifacts
under `kaohsiung_microclimate_lstm/models/` are tracked, so the API works out of the box without
retraining. See [`docs/dataset_guide.md`](docs/dataset_guide.md) for data sources, how to
regenerate the training data locally, and how raw data becomes trained models.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r kaohsiung_microclimate_lstm/requirements.txt
Copy-Item .env.example .env
```

Both requirements files are required. `requirements.txt` covers the FastAPI app itself;
`kaohsiung_microclimate_lstm/requirements.txt` covers the modeling/prediction pipeline
(pandas, scikit-learn, torch, pyarrow, etc.). The server starts fine with only the first one
installed, but every dispatch-risk endpoint (`/api/v1/dispatch/risk`, `/dispatch-risk-demo`,
and friends) will fail at request time without the second, since those imports are lazy.

For frontend integration, set `CORS_ALLOWED_ORIGINS` in `.env` to the frontend's actual
origin(s) (comma-separated) once known; it defaults to `*` (open) for local development.

Optional CWA API access:

```text
CWA_API_KEY=your-cwa-open-data-key
```

Do not commit real API keys.

## Data Refresh Controls

The dispatch demo page includes a `抓取最新資料` button. It calls:

```text
POST /admin/fetch-microclimate-sources
```

That endpoint runs the same four source refreshers used by the scheduler foundation:

- KHWD/KHTD/KHAW port-local observations
- O-B0075-001 marine realtime observations
- nearby CWA live observations for the six C0V stations
- CWA forecast release history logging

Automatic refresh is prepared but disabled by default to avoid extra background memory use. To enable it later, edit `kaohsiung_microclimate_lstm/config.yaml`:

```yaml
auto_fetch_scheduler:
  enabled: true
```

Then restart the API service. Default intervals are KHWD 10 minutes, marine realtime 240 minutes, nearby CWA live 15 minutes, and CWA forecast history 180 minutes. Check status with:

```text
GET /admin/scheduler-status
```

## CLI

The v2.0 CLI wrapper is available as:

```powershell
python -m kaohsiung_microclimate_lstm.src.cli --help
```

Examples:

```powershell
python -m kaohsiung_microclimate_lstm.src.cli evaluate --station-id 467441 --target wind_speed_gust --config kaohsiung_microclimate_lstm/config.yaml

python -m kaohsiung_microclimate_lstm.src.cli system-audit --target-area KHH --config kaohsiung_microclimate_lstm/config.yaml
```

v1.3 data and benchmark utilities:

```powershell
python -m kaohsiung_microclimate_lstm.src.data.fetch_marine_history --output-dir kaohsiung_microclimate_lstm/data/raw/observed_hourly

python -m kaohsiung_microclimate_lstm.src.tools.run_model_benchmark --dataset path/to/training.csv --target wind_speed --output-dir kaohsiung_microclimate_lstm/results/model_benchmark_v13
```

## Verification

Run the main project test suite:

```powershell
python -m pytest
```

The root `pytest.ini` intentionally scopes default tests to `tests/`.

## Specification Files

The active v1.3 specification and earlier v2.0 specification files are stored at the repository
root, but are excluded from git (`*規格書*.md` in `.gitignore`) since they are working documents
for coordinating implementation rounds, not shipped project artifacts:

```text
高雄港微氣候預測_專案規格書_v1.3.md
高雄港微氣候預測系統_v2.0_規格書_前半部.md
高雄港微氣候預測系統_v2.0_規格書_後半部.md
```

Implementation progress is tracked in:

```text
docs/spec_v13_implementation_summary.md
```
