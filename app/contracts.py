from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.models import TAIPEI, TwPortObservation
from app.storage import observation_status


SCHEMA_VERSION = "microclimate.v1"
TIME_ZONE = "Asia/Taipei"
SPEC_VERSION = "v1.3"
DEFAULT_RUNTIME_MODEL_VERSION = "kaohsiung_port_dispatch_risk_v1.3"
PROJECT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "kaohsiung_microclimate_lstm" / "config.yaml"


def runtime_model_version(config_path: str | Path = PROJECT_CONFIG_PATH) -> str:
    path = Path(config_path)
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return DEFAULT_RUNTIME_MODEL_VERSION
    return str(cfg.get("project", {}).get("model_version") or DEFAULT_RUNTIME_MODEL_VERSION)


SYSTEM_INFO = {
    "project_name": "Kaohsiung Port Microclimate Prediction System",
    "spec_version": SPEC_VERSION,
    "runtime_model_version": runtime_model_version(),
    "target_area": {
        "port_code": "KHH",
        "name": "Kaohsiung Port",
        "timezone": TIME_ZONE,
    },
    "objectives": {
        "primary": [
            "Predict short-term port-area microclimate conditions at 30, 60, 90, and 120 minute anchors.",
            "Support dispatch-risk decisions using wind, gust, precipitation, tide, and visibility signals.",
            "Prefer port-local observations and keep fallback station usage explicit in API traces.",
        ],
        "secondary": [
            "Integrate CWA, CODiS, TWPort, marine, tide, and local historical data sources.",
            "Provide reproducible training, evaluation, reporting, and API outputs.",
            "Expose data quality and model-selection status for operations and debugging.",
        ],
    },
    "architecture_layers": [
        "data_collection",
        "data_preprocessing_quality_control",
        "feature_engineering",
        "model_training_evaluation",
        "prediction_dispatch_risk",
        "api_dashboard_reporting",
    ],
    "data_sources": [
        "TWPort port-local observations",
        "CWA Open Data observations and forecasts",
        "CODiS historical rainfall data",
        "CWA marine observations",
        "Tide and wave observations",
    ],
    "prediction_targets": [
        "wind_speed",
        "wind_gust",
        "precipitation_1hr",
        "tide_level",
        "visibility",
    ],
    "tech_stack": {
        "language": "Python 3.9+",
        "api": "FastAPI",
        "data": ["pandas", "numpy", "SQLite", "Parquet"],
        "ml": ["PyTorch", "scikit-learn", "joblib"],
        "config": ["PyYAML", "python-dotenv"],
        "testing": ["pytest"],
    },
}
SYSTEM_REQUIREMENTS = {
    "functional": [
        {
            "id": "FR-001",
            "name": "data_collection",
            "status": "implemented",
            "summary": "Collect TWPort, CWA, CWA history, CWA marine, CODiS fallback, and port-local station data.",
            "implementation": [
                "app.collectors.twport",
                "app.collectors.cwa",
                "app.collectors.cwa_historyapi",
                "app.collectors.cwa_marine_history",
                "app.collectors.cwa_history",
                "kaohsiung_microclimate_lstm.src.tools.fetch_port_local_stations",
            ],
            "verification": ["tests/test_twport_parser.py", "tests/test_cwa_*", "tests/test_fetch_port_local_stations.py"],
        },
        {
            "id": "FR-002",
            "name": "data_preprocessing",
            "status": "implemented",
            "summary": "Normalize source fields, resample time-series data, mark invalid gaps, and create processed datasets.",
            "implementation": [
                "kaohsiung_microclimate_lstm.src.preprocess",
                "kaohsiung_microclimate_lstm.src.data.historical_weather_normalizer",
                "kaohsiung_microclimate_lstm.src.data.port_local_station_normalizer",
            ],
            "verification": ["tests/test_lstm_baseline_preprocess.py", "tests/test_port_local_station_normalizer.py"],
        },
        {
            "id": "FR-003",
            "name": "feature_engineering",
            "status": "implemented",
            "summary": "Build temporal, multi-station, nearby CWA, port-local wind, and rain-prior features.",
            "implementation": [
                "kaohsiung_microclimate_lstm.src.data.feature_builder",
                "kaohsiung_microclimate_lstm.src.data.nearby_aggregation",
                "kaohsiung_microclimate_lstm.src.data.port_local_wind_aggregation",
            ],
            "verification": ["tests/test_feature_builder.py", "tests/test_nearby_aggregation.py", "tests/test_port_local_wind_aggregation.py"],
        },
        {
            "id": "FR-004",
            "name": "model_training",
            "status": "implemented",
            "summary": "Train LSTM baselines, port-local models, nearby CWA historical models, and maintain registry metadata.",
            "implementation": [
                "kaohsiung_microclimate_lstm.src.train",
                "kaohsiung_microclimate_lstm.src.training.train_port_local_model",
                "kaohsiung_microclimate_lstm.src.training.train_nearby_cwa_historical_model",
                "kaohsiung_microclimate_lstm.src.training_orchestration",
            ],
            "verification": ["tests/test_train_port_local_model.py", "tests/test_train_nearby_cwa_historical_model.py", "tests/test_dispatch_risk_v34_training_orchestration.py"],
        },
        {
            "id": "FR-005",
            "name": "model_evaluation",
            "status": "implemented",
            "summary": "Evaluate regression, rainfall, extreme-value, CWA comparison, and Markdown report outputs.",
            "implementation": [
                "kaohsiung_microclimate_lstm.src.evaluate",
                "kaohsiung_microclimate_lstm.src.evaluation.metrics",
                "kaohsiung_microclimate_lstm.src.evaluation.validators",
                "kaohsiung_microclimate_lstm.src.evaluation.comparators",
                "kaohsiung_microclimate_lstm.src.evaluation.report_generator",
            ],
            "verification": ["tests/test_v20_evaluation_*.py"],
        },
        {
            "id": "FR-006",
            "name": "realtime_prediction",
            "status": "implemented",
            "summary": "Expose 30-120 minute prediction anchors and dispatch-risk JSON through API and CLI.",
            "implementation": [
                "app.api.build_dispatch_risk_response",
                "kaohsiung_microclimate_lstm.src.predict",
                "kaohsiung_microclimate_lstm.src.cli",
            ],
            "verification": ["tests/test_dispatch_risk_api*.py", "tests/test_predict_dispatch_risk_*.py", "tests/test_v20_cli.py"],
        },
        {
            "id": "FR-007",
            "name": "result_visualization",
            "status": "partially_implemented",
            "summary": "HTML dashboard and dispatch-risk demo exist; static plot exports exist for model training/evaluation, but full PNG/SVG/HTML visualization export coverage remains chapter-specific follow-up.",
            "implementation": ["app.api.render_dashboard", "app.api.render_dispatch_risk_demo", "kaohsiung_microclimate_lstm.src.plot_training"],
            "verification": ["tests/test_dispatch_risk_demo_page.py"],
        },
    ],
    "non_functional": [
        {
            "id": "NFR-001",
            "name": "performance",
            "status": "tracked",
            "summary": "Configured for short-horizon API prediction and bounded training; exact runtime targets are tracked through tests and audit reports rather than guaranteed on every machine.",
            "implementation": ["kaohsiung_microclimate_lstm.config.yaml", "kaohsiung_microclimate_lstm.src.system_audit"],
            "verification": ["tests/test_dispatch_risk_v35_system_audit.py"],
        },
        {
            "id": "NFR-002",
            "name": "reliability",
            "status": "implemented",
            "summary": "Health checks, stale-data status, fallback traces, station-role validation, and model-selection reports support operational reliability.",
            "implementation": ["app.api.health", "app.storage.observation_status", "kaohsiung_microclimate_lstm.src.selection.model_selection_engine"],
            "verification": ["tests/test_app_storage_status.py", "tests/test_dispatch_risk_v33_station_roles.py", "tests/test_dispatch_risk_v34_api_contract.py"],
        },
        {
            "id": "NFR-003",
            "name": "maintainability",
            "status": "implemented",
            "summary": "Stable API contracts, pytest coverage, modular source layout, and chapter audit documentation support maintainability.",
            "implementation": ["app.contracts", "tests", "docs/spec_v20_implementation_audit.md"],
            "verification": ["python -m pytest"],
        },
        {
            "id": "NFR-004",
            "name": "scalability",
            "status": "partially_implemented",
            "summary": "Station pools, source-specific collectors, and modular model selection support extension; distributed deployment is not implemented in this repository.",
            "implementation": ["kaohsiung_microclimate_lstm.config.station_pool.yaml", "kaohsiung_microclimate_lstm.src.data.station_pool"],
            "verification": ["tests/test_station_pool.py", "tests/test_station_priority.py"],
        },
        {
            "id": "NFR-005",
            "name": "usability",
            "status": "implemented",
            "summary": "README, CLI, FastAPI docs, schema endpoint, system-info endpoint, demo page, and dashboard payloads provide operator-facing usability.",
            "implementation": ["README.md", "kaohsiung_microclimate_lstm.src.cli", "app.api"],
            "verification": ["tests/test_system_info_api.py", "tests/test_v20_cli.py", "tests/test_dispatch_risk_demo_page.py"],
        },
    ],
}
DATA_SPEC = {
    "sources": [
        {
            "id": "cwa",
            "name": "CWA observations and forecasts",
            "expected_update_minutes": 60,
            "freshness_threshold_minutes": 75,
            "formats": ["JSON", "CSV"],
            "station_examples": ["466940", "467440", "467480", "467441"],
            "implementation": ["app.collectors.cwa", "app.collectors.cwa_historyapi", "kaohsiung_microclimate_lstm.src.cwa"],
        },
        {
            "id": "codis",
            "name": "CODiS rainfall observations and historical fallback",
            "expected_update_minutes": 60,
            "freshness_threshold_minutes": 75,
            "formats": ["CSV"],
            "station_examples": ["C0V200", "C0V210", "C0V220", "C0V890"],
            "implementation": ["app.collectors.cwa_history", "kaohsiung_microclimate_lstm.src.data.fetch_codis_10min"],
        },
        {
            "id": "twport",
            "name": "TWPort port-local marine and microclimate observations",
            "expected_update_minutes": 10,
            "freshness_threshold_minutes": 45,
            "formats": ["HTML", "JSON-derived records"],
            "station_examples": ["KHWD01", "KHWD04", "KHWD05", "KHWD06", "KHWD07", "KHWD08"],
            "implementation": ["app.collectors.twport", "kaohsiung_microclimate_lstm.src.data.port_local_twport_client"],
        },
        {
            "id": "cwa_marine",
            "name": "CWA marine observations",
            "expected_update_minutes": 60,
            "freshness_threshold_minutes": 75,
            "formats": ["JSON"],
            "station_examples": ["C4Q01", "C4Q02", "C4P01"],
            "implementation": ["app.collectors.cwa_marine_history"],
        },
    ],
    "variables": {
        "air_temperature": {"unit": "C", "dtype": "float", "valid_range": [-5, 45], "missing_values": [None, -999]},
        "air_pressure": {"unit": "hPa", "dtype": "float", "valid_range": [950, 1050], "missing_values": [None, -999]},
        "relative_humidity": {"unit": "%", "dtype": "float", "valid_range": [0, 100], "missing_values": [None, -999]},
        "precipitation_10min": {"unit": "mm", "dtype": "float", "valid_range": [0, 100], "missing_values": [None, -999, -998]},
        "precipitation_1hr": {"unit": "mm", "dtype": "float", "valid_range": [0, 200], "missing_values": [None, -999, -998]},
        "precipitation_24hr": {"unit": "mm", "dtype": "float", "valid_range": [0, 500], "missing_values": [None, -999, -998]},
        "wind_speed": {"unit": "m/s", "dtype": "float", "valid_range": [0, 60], "missing_values": [None, -999]},
        "wind_gust": {"unit": "m/s", "dtype": "float", "valid_range": [0, 80], "missing_values": [None, -999]},
        "wind_direction": {"unit": "degree", "dtype": "float", "valid_range": [0, 360], "missing_values": [None, -999]},
        "visibility": {"unit": "m", "dtype": "float", "valid_range": [0, 30000], "missing_values": [None, -999]},
        "tide_level": {"unit": "source-specific", "dtype": "float", "valid_range": [-200, 600], "missing_values": [None, -999]},
        "wave_height": {"unit": "m", "dtype": "float", "valid_range": [0, 10], "missing_values": [None, -999]},
    },
    "quality_standards": {
        "station_missing_ratio_max": 0.10,
        "variable_missing_ratio_max": 0.05,
        "continuous_missing_hours_max": 2,
        "outlier_methods": ["valid_range", "3_sigma", "1.5_iqr", "physical_rate_limit"],
        "freshness_thresholds_minutes": {
            "cwa": 15,
            "codis": 20,
            "twport": 45,
            "stored_data_warning": 60,
        },
    },
    "storage": {
        "sqlite_table": "microclimate_observations",
        "raw_layout": {
            "cwa": "data/raw/cwa/{YYYY}/{MM}/{StationID}_{YYYYMMDD}.csv",
            "codis": "data/raw/codis/{YYYY}/{MM}/{StationID}_{YYYYMMDD}.csv",
            "harbor": "data/raw/harbor/{YYYY}/{MM}/harbor_{YYYYMMDD}.json",
            "observed_hourly": "kaohsiung_microclimate_lstm/data/raw/observed_hourly/{station_id}.csv",
        },
        "processed_layout": {
            "merged": "kaohsiung_microclimate_lstm/data/processed/*.parquet",
            "features": "kaohsiung_microclimate_lstm/data/processed/*.npz",
            "quality_report": "kaohsiung_microclimate_lstm/data/processed/data_quality_report.json",
        },
        "canonical_columns": [
            "obs_time",
            "station_id",
            "source",
            "device_type",
            "air_temperature",
            "air_pressure",
            "relative_humidity",
            "precipitation_10min",
            "precipitation_1hr",
            "precipitation_24hr",
            "wind_speed",
            "wind_direction",
            "wind_gust",
            "visibility",
            "tide_level",
            "wave_height",
            "confidence",
            "stale",
        ],
    },
    "quality_report_schema": {
        "summary": ["total_records", "valid_records", "invalid_records", "data_completeness"],
        "by_station": ["completeness", "missing_hours", "outliers_detected", "quality_score"],
        "by_variable": ["completeness", "mean", "std", "min", "max", "outliers"],
        "issues": ["type", "station", "time_range", "variables", "severity", "action"],
        "recommendations": "list[str]",
    },
}
FEATURE_SPEC = {
    "categories": [
        {"id": "historical_lag", "expected_count": "40-50", "priority": "high", "examples": ["rainfall_lag_0.5h", "wind_speed_lag_1h"]},
        {"id": "rolling_statistics", "expected_count": "40-50", "priority": "high", "examples": ["rainfall_roll_3h_sum", "wind_speed_roll_1h_std"]},
        {"id": "change_rate", "expected_count": "20-25", "priority": "high", "examples": ["pressure_change_3h", "temp_change_1h"]},
        {"id": "temporal", "expected_count": "10-15", "priority": "high", "examples": ["hour_sin", "hour_cos", "is_afternoon"]},
        {"id": "meteorological_physics", "expected_count": "30-40", "priority": "critical", "examples": ["pressure_trend_3h", "temp_dewpoint_diff", "wind_u"]},
        {"id": "spatial", "expected_count": "20-30", "priority": "medium", "examples": ["rainfall_neighbors_mean", "rainfall_upwind_5km"]},
        {"id": "interaction", "expected_count": "5-10", "priority": "medium", "examples": ["pressure_humidity_interaction", "dewpoint_wind_interaction"]},
    ],
    "generation": {
        "lag_hours": [0.5, 1, 2, 3, 6],
        "rolling_windows_hours": [1, 3, 6],
        "rolling_statistics": ["mean", "max", "min", "std", "sum"],
        "change_hours": [0.5, 1, 3, 6],
        "cyclic_features": ["hour_sin", "hour_cos", "doy_sin", "doy_cos", "month_sin", "month_cos"],
        "special_period_features": ["is_night", "is_dawn", "is_afternoon", "is_typhoon_season"],
        "wind_features": ["wind_u", "wind_v", "wind_speed_change_1h", "wind_direction_change_1h", "wind_speed_std_1h", "wind_speed_std_3h"],
        "pressure_features": ["pressure_current", "pressure_change_1h", "pressure_change_3h", "pressure_trend_3h", "pressure_acceleration_1h"],
    },
    "key_features_by_target": {
        "precipitation_1hr": ["pressure_change_3h", "rainfall_lag_0.5h", "rainfall_roll_3h_sum", "temp_dewpoint_diff", "rainfall_neighbors_mean"],
        "wind_speed_gust": ["wind_speed_lag_0.5h", "wind_u_lag_1h", "wind_v_lag_1h", "wind_speed_std_3h", "pressure_change_1h"],
        "visibility": ["temp_dewpoint_diff", "visibility_lag_0.5h", "humidity_current", "dewpoint_wind_interaction", "is_night"],
    },
    "selection": {
        "importance_threshold_default": 0.001,
        "cumulative_importance_default": 0.95,
        "correlation_threshold_default": 0.95,
        "target_feature_count_guidance": {
            "rainfall": "80-100",
            "general": "50-80",
        },
    },
    "implementation": [
        "kaohsiung_microclimate_lstm.src.data.feature_engineering",
        "kaohsiung_microclimate_lstm.src.data.feature_builder",
        "kaohsiung_microclimate_lstm.src.preprocess",
    ],
    "phases": [
        {"phase": 1, "name": "basic_temporal", "status": "implemented"},
        {"phase": 2, "name": "meteorological_physics", "status": "implemented"},
        {"phase": 3, "name": "spatial_features", "status": "partially_implemented"},
        {"phase": 4, "name": "optimization_selection", "status": "implemented"},
    ],
}
MODEL_SPEC = {
    "strategy": {
        "modeling_unit": "per_target_variable",
        "forecast_anchors_minutes": [30, 60, 90, 120],
        "implemented_runtime_family": ["lstm", "two_stage_lstm", "multitask_lstm", "spatial_lstm", "tree_baseline", "harmonic_tide"],
        "selection_policy": "port_local_model -> port_local_postprocess -> nearby_cwa_historical_model -> fallback_baseline",
    },
    "target_models": {
        "precipitation_1hr": {
            "spec_primary_algorithms": ["XGBoost", "LightGBM"],
            "implemented_models": ["TwoStageRainLSTM", "RainfallModel", "RainfallCascadeModel", "nearby_cwa_rain_probability"],
            "postprocessing": ["clip_negative", "smooth_small_values", "cwa_pop_prior", "rain_probability_rules"],
        },
        "wind_speed": {
            "spec_primary_algorithms": ["RandomForest", "XGBoost"],
            "implemented_models": ["MultiTaskWindLSTM", "WindModel", "port_local_tree_baseline", "nearby_cwa_historical_model"],
            "postprocessing": ["clip_negative", "port_local_wind_postprocess"],
        },
        "wind_gust": {
            "spec_primary_algorithms": ["LightGBM"],
            "implemented_models": ["MultiTaskWindLSTM", "GustModel", "port_local_tree_baseline", "nearby_cwa_historical_model"],
            "postprocessing": ["clip_negative", "enforce_gust_ge_wind", "port_local_gust_postprocess"],
        },
        "visibility": {
            "spec_primary_algorithms": ["XGBoost"],
            "implemented_models": ["BaselineLSTM", "VisibilityModel"],
            "postprocessing": ["clip_range", "visibility_grade"],
        },
        "tide_level": {
            "spec_primary_algorithms": ["harmonic_analysis", "ML adjustment"],
            "implemented_models": ["harmonic_tide_model", "BaselineLSTM"],
            "postprocessing": ["harmonic_reconstruction"],
        },
    },
    "model_classes": [
        "BaseWeatherModel",
        "RainfallModel",
        "RainfallCascadeModel",
        "WindModel",
        "GustModel",
        "VisibilityModel",
        "EnsembleModel",
        "Tide harmonic model",
    ],
    "training_pipeline": [
        "load_observations",
        "build_window_bundle",
        "chronological_split",
        "train_model",
        "evaluate_model",
        "model_registry",
        "training_orchestration",
    ],
    "artifacts": {
        "lstm_checkpoints": "kaohsiung_microclimate_lstm/models/checkpoints/{station_id}_{target_group}_best.pt",
        "tabular_models": "kaohsiung_microclimate_lstm/models/{family}/{target}.joblib",
        "tide_harmonic": "kaohsiung_microclimate_lstm/models/tide/{station_id}_harmonic_coef.pkl",
        "registry": "kaohsiung_microclimate_lstm/models/model_registry.json",
        "metrics": "kaohsiung_microclimate_lstm/results/evaluation/*_metrics.json",
    },
    "implementation": [
        "kaohsiung_microclimate_lstm.src.model",
        "kaohsiung_microclimate_lstm.src.model_wrappers",
        "kaohsiung_microclimate_lstm.src.train",
        "kaohsiung_microclimate_lstm.src.training_orchestration",
        "kaohsiung_microclimate_lstm.src.tide.harmonic_model",
        "kaohsiung_microclimate_lstm.src.model_registry",
    ],
}
EVALUATION_SPEC = {
    "basic_metrics": ["rmse", "mae", "r2", "mape", "medae", "bias", "quantile_errors", "skill_score"],
    "rainfall_metrics": {
        "thresholds_mm": {"trace": 0.1, "light": 2.0, "moderate": 10.0, "heavy": 30.0, "extreme": 70.0},
        "classification_metrics": ["pod", "far", "csi", "hss", "ets", "hits", "misses", "false_alarms", "correct_negatives"],
    },
    "extreme_value_assessment": {
        "default_percentile": 90,
        "metrics": ["extreme_mae", "extreme_rmse", "extreme_capture_rate"],
    },
    "validation": {
        "time_series_split": {"n_splits": 5, "test_size": 0.2, "gap": 0},
        "rolling_window": {"train_size": "configurable", "test_size": "configurable", "step_size": "defaults_to_test_size"},
    },
    "cwa_comparison": {
        "enabled": True,
        "metrics": ["rmse", "mae", "pod", "far", "csi"],
        "scenarios": ["all", "clear", "rainy", "heavy_rain", "high_wind", "low_visibility"],
    },
    "reporting": {
        "format": "Markdown",
        "sections": ["basic_stats", "metrics", "feature_importance", "error_analysis", "optional_plots"],
    },
    "implementation": [
        "kaohsiung_microclimate_lstm.src.evaluate",
        "kaohsiung_microclimate_lstm.src.evaluation.metrics",
        "kaohsiung_microclimate_lstm.src.evaluation.validators",
        "kaohsiung_microclimate_lstm.src.evaluation.comparators",
        "kaohsiung_microclimate_lstm.src.evaluation.report_generator",
    ],
}
API_SPEC = {
    "internal_python_api": {
        "DataAPI": {
            "module": "kaohsiung_microclimate_lstm.src.data.api",
            "methods": ["collect_data", "preprocess_data", "merge_multi_source"],
        },
        "FeatureAPI": {
            "module": "kaohsiung_microclimate_lstm.src.features.api",
            "methods": ["create_features", "select_features"],
        },
        "ModelAPI": {
            "module": "kaohsiung_microclimate_lstm.src.models.api",
            "methods": ["train_model", "load_model", "predict"],
        },
    },
    "cli": {
        "module": "kaohsiung_microclimate_lstm.src.cli",
        "entrypoint": "python -m kaohsiung_microclimate_lstm.src.cli",
        "commands": ["download", "preprocess", "features", "train", "evaluate", "predict", "dispatch-risk", "system-audit", "run-all"],
    },
    "http_api": {
        "framework": "FastAPI",
        "stable_endpoints": [
            "/api/v1/schema",
            "/api/v1/system/info",
            "/api/v1/system/requirements",
            "/api/v1/system/data-spec",
            "/api/v1/system/feature-spec",
            "/api/v1/system/model-spec",
            "/api/v1/system/evaluation-spec",
            "/api/v1/system/api-spec",
            "/api/v1/system/deployment-spec",
            "/api/v1/system/testing-spec",
            "/api/v1/system/schedule-spec",
            "/api/v1/system/appendix-spec",
            "/api/v1/microclimate/current",
            "/api/v1/microclimate/forecast",
            "/api/v1/dispatch/risk",
            "/api/v1/dispatch/model-status",
            "/api/v1/dispatch/station-usage",
            "/api/v1/dispatch/system-audit",
        ],
    },
}
TESTING_SPEC = {
    "strategy": [
        {"type": "unit", "scope": "individual functions and methods", "frequency": "every commit", "target": "coverage > 80%"},
        {"type": "integration", "scope": "module interactions", "frequency": "daily", "target": "module collaboration remains valid"},
        {"type": "system", "scope": "end-to-end workflows", "frequency": "weekly", "target": "complete workflow validation"},
        {"type": "performance", "scope": "runtime efficiency", "frequency": "monthly", "target": "performance requirements remain acceptable"},
    ],
    "unit_test_examples": {
        "feature_engineering": [
            "create_lag_features",
            "create_rolling_features",
            "create_cyclic_time_features",
            "create_special_period_features",
            "create_interaction_features",
        ],
    },
    "ci": {
        "provider": "GitHub Actions",
        "workflow": ".github/workflows/ci.yml",
        "python_versions": ["3.9", "3.10", "3.11"],
        "commands": ["python -m pytest --cov=. --cov-report=xml --cov-fail-under=80"],
        "coverage_report": "coverage.xml",
    },
    "local_commands": {
        "all_tests": "python -m pytest -q",
        "coverage": "python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=80",
    },
}
SCHEDULE_SPEC = {
    "phases": [
        {"id": "phase_1", "name": "project_setup_and_data_collection", "duration_days": 13, "deliverables": ["project_structure", "data_source_connection", "data_validation_cleaning"]},
        {"id": "phase_2", "name": "feature_engineering", "duration_days": 19, "deliverables": ["basic_features", "meteorological_features", "spatial_features"]},
        {"id": "phase_3", "name": "model_development", "duration_days": 17, "deliverables": ["rainfall_model", "wind_model", "visibility_model"]},
        {"id": "phase_4", "name": "evaluation_and_optimization", "duration_days": 15, "deliverables": ["model_evaluation", "parameter_tuning", "report_generation"]},
        {"id": "phase_5", "name": "integration_and_deployment", "duration_days": 10, "deliverables": ["system_integration", "deployment_testing", "production_deployment"]},
    ],
    "milestones": [
        {"id": "M1", "name": "data_pipeline_complete", "week": 2},
        {"id": "M2", "name": "feature_engineering_complete", "week": 4},
        {"id": "M3", "name": "basic_model_complete", "week": 6},
        {"id": "M4", "name": "performance_optimization_complete", "week": 8},
        {"id": "M5", "name": "system_deployment", "week": 10},
    ],
    "timeline_format": "mermaid_gantt",
}
APPENDIX_SPEC = {
    "project_templates": {
        "setup_project_structure": {
            "linux": "scripts/setup_project_structure.sh",
            "windows": "scripts/setup_project_structure.ps1",
        },
        "requirements": ["requirements.txt", "kaohsiung_microclimate_lstm/requirements.txt"],
        "package_setup": "setup.py",
        "makefile": "Makefile",
        "gitignore": ".gitignore",
    },
    "documented_tree": [
        "config",
        "data/raw",
        "data/processed",
        "kaohsiung_microclimate_lstm/src",
        "kaohsiung_microclimate_lstm/models",
        "kaohsiung_microclimate_lstm/results",
        "tests",
        "docs",
        "logs",
    ],
    "entrypoints": {
        "api": "uvicorn app.api:app --reload",
        "cli": "python -m kaohsiung_microclimate_lstm.src.cli",
    },
}
DEPLOYMENT_SPEC = {
    "hardware": {
        "minimum": {
            "cpu_cores": 4,
            "memory_gb": 8,
            "storage": "100GB SSD",
            "network": "10 Mbps",
        },
        "recommended": {
            "cpu_cores": 8,
            "memory_gb": 16,
            "storage": "500GB SSD",
            "network": "100 Mbps",
        },
    },
    "software": {
        "operating_systems": ["Ubuntu 20.04+", "CentOS 8+", "Windows 10+"],
        "python": "3.9+",
        "git": "2.0+",
        "primary_entrypoints": ["uvicorn app.api:app", "python -m kaohsiung_microclimate_lstm.src.cli"],
    },
    "installation": {
        "linux_script": "install.sh",
        "windows_script": "install.ps1",
        "steps": [
            "check_python_version",
            "create_virtual_environment",
            "upgrade_pip",
            "install_requirements",
            "create_project_directories",
            "copy_env_example_when_missing",
        ],
        "setup_script": "scripts/setup_project_structure.ps1",
    },
    "environment_variables": {
        "required_for_runtime": ["DATABASE_URL", "DATA_DIR", "MODEL_DIR", "LOG_DIR", "ENV", "DEBUG", "LOG_LEVEL"],
        "required_for_external_fetch": ["CWA_API_KEY"],
        "optional": ["CODIS_API_KEY", "TWPORT_BASE_URL", "REQUEST_TIMEOUT_SECONDS", "ALERT_WIND_SPEED", "ALERT_WIND_GUST"],
        "template": ".env.example",
    },
    "logging": {
        "config_path": "config/logging_config.yaml",
        "handlers": ["console", "file", "error_file"],
        "files": ["logs/app.log", "logs/error.log"],
        "rotation": {"max_bytes": 10485760, "backup_count": 5},
    },
    "monitoring": {
        "health_endpoint": "/health",
        "system_audit_endpoint": "/api/v1/dispatch/system-audit",
        "model_status_endpoint": "/api/v1/dispatch/model-status",
        "station_usage_endpoint": "/api/v1/dispatch/station-usage",
    },
}
OBSERVATION_CONTRACT = {
    "record_id": "Stable string composed from source/device/station/forecast flag/observed_at.",
    "source": "Data source id, e.g. twport, cwa, cwa_historyapi, cwa_marine_history.",
    "device_type": "Normalized data type, e.g. WIND, WEATHER, MARINE, TIDE, WAVE.",
    "station": {
        "station_id": "Source station identifier.",
        "station_name": "Human-readable station name.",
        "location": "Station location or marine area.",
        "port_code": "Port code when supplied by source.",
        "longitude": "Decimal degrees, WGS84 when available.",
        "latitude": "Decimal degrees, WGS84 when available.",
        "elevation": "Meters when available.",
    },
    "time": {
        "observed_at": "ISO8601 Asia/Taipei observation time.",
        "fetched_at": "ISO8601 Asia/Taipei fetch time, nullable for derived records.",
        "time_zone": TIME_ZONE,
    },
    "metrics": {
        "wind_speed_mps": "m/s",
        "wind_gust_mps": "m/s",
        "wind_direction_deg": "degrees 0-360",
        "wind_gust_direction_deg": "degrees 0-360",
        "precipitation_10min_mm": "mm",
        "precipitation_1hr_mm": "mm",
        "precipitation_24hr_mm": "mm",
        "air_temperature_c": "Celsius",
        "relative_humidity_percent": "%",
        "air_pressure_hpa": "hPa when supplied by source",
        "visibility_m": "meters",
        "tide_level": "Unit indicated by tide_level_unit",
        "tide_level_unit": "m, cm, raw, or source-specific nullable string",
        "wave_height_m": "meters",
        "wave_period_s": "seconds",
        "wave_max_height_m": "meters",
        "current_speed_mps": "m/s",
        "current_direction_deg": "degrees 0-360",
    },
    "quality": {
        "is_forecast": "boolean",
        "confidence": "high, medium, low",
        "stale_at_fetch": "boolean from collector/storage time",
        "status_level": "current, stale, outage, or null when not evaluated",
        "status_label": "Human-readable status label or null",
        "is_stale_now": "boolean or null when not evaluated",
        "obs_age_minutes": "integer minutes or null",
        "fetch_age_minutes": "integer minutes or null",
        "threshold_minutes": "integer minutes or null",
        "expected_update_interval": "Human-readable expected update interval or null",
    },
}


def schema_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/schema",
        metadata={
            "schema_version": SCHEMA_VERSION,
            "compatibility": "Fields documented here are stable for v1. Additive metadata may appear; breaking changes require a new schema_version.",
            "observation_record": OBSERVATION_CONTRACT,
            "stable_endpoints": [
                "/api/v1/microclimate/current",
                "/api/v1/microclimate/forecast",
                "/api/v1/dispatch/risk",
                "/api/v1/system/info",
                "/api/v1/system/requirements",
                "/api/v1/system/data-spec",
                "/api/v1/system/feature-spec",
                "/api/v1/system/model-spec",
                "/api/v1/system/evaluation-spec",
                "/api/v1/system/api-spec",
                "/api/v1/system/deployment-spec",
                "/api/v1/system/testing-spec",
                "/api/v1/system/schedule-spec",
                "/api/v1/system/appendix-spec",
                "/api/v1/cwa/history",
                "/api/v1/schema",
            ],
        },
        data=[],
        data_quality={"record_count": 0},
    )


def system_info_response() -> dict[str, Any]:
    info = {**SYSTEM_INFO, "runtime_model_version": runtime_model_version()}
    return response_envelope(
        endpoint="/api/v1/system/info",
        metadata={
            "contract": "Stable system overview aligned with the v1.3 specification chapter 1.",
        },
        data=[info],
        data_quality={"record_count": 1},
    )


def system_requirements_response() -> dict[str, Any]:
    functional = SYSTEM_REQUIREMENTS["functional"]
    non_functional = SYSTEM_REQUIREMENTS["non_functional"]
    statuses = [item["status"] for item in functional + non_functional]
    return response_envelope(
        endpoint="/api/v1/system/requirements",
        metadata={
            "contract": "Requirement traceability matrix aligned with the v1.3 specification chapter 2.",
            "functional_count": len(functional),
            "non_functional_count": len(non_functional),
            "status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                "functional": functional,
                "non_functional": non_functional,
            }
        ],
        data_quality={"record_count": len(functional) + len(non_functional)},
    )


def data_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/data-spec",
        metadata={
            "contract": "Data source, quality, storage, and report schema aligned with the v1.3 specification chapter 3.",
            "source_count": len(DATA_SPEC["sources"]),
            "variable_count": len(DATA_SPEC["variables"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **DATA_SPEC,
            }
        ],
        data_quality={"record_count": len(DATA_SPEC["sources"])},
    )


def feature_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/feature-spec",
        metadata={
            "contract": "Feature taxonomy, generation rules, and selection strategy aligned with the v1.3 specification chapter 4.",
            "category_count": len(FEATURE_SPEC["categories"]),
            "phase_count": len(FEATURE_SPEC["phases"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **FEATURE_SPEC,
            }
        ],
        data_quality={"record_count": len(FEATURE_SPEC["categories"])},
    )


def model_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/model-spec",
        metadata={
            "contract": "Model architecture, target strategy, artifacts, and training pipeline aligned with the v1.3 specification chapter 5.",
            "target_model_count": len(MODEL_SPEC["target_models"]),
            "class_count": len(MODEL_SPEC["model_classes"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **MODEL_SPEC,
            }
        ],
        data_quality={"record_count": len(MODEL_SPEC["target_models"])},
    )


def evaluation_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/evaluation-spec",
        metadata={
            "contract": "Evaluation metrics, validation strategy, CWA comparison, and report generation aligned with the v1.3 specification chapter 6.",
            "basic_metric_count": len(EVALUATION_SPEC["basic_metrics"]),
            "rainfall_metric_count": len(EVALUATION_SPEC["rainfall_metrics"]["classification_metrics"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **EVALUATION_SPEC,
            }
        ],
        data_quality={"record_count": 1},
    )


def api_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/api-spec",
        metadata={
            "contract": "Internal Python API, CLI, and HTTP API contract aligned with the v1.3 specification chapter 7.",
            "cli_command_count": len(API_SPEC["cli"]["commands"]),
            "internal_api_count": len(API_SPEC["internal_python_api"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **API_SPEC,
            }
        ],
        data_quality={"record_count": 1},
    )


def deployment_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/deployment-spec",
        metadata={
            "contract": "Deployment environment, installation, logging, and monitoring contract aligned with the v1.3 specification chapter 8.",
            "minimum_cpu_cores": DEPLOYMENT_SPEC["hardware"]["minimum"]["cpu_cores"],
            "minimum_memory_gb": DEPLOYMENT_SPEC["hardware"]["minimum"]["memory_gb"],
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **DEPLOYMENT_SPEC,
            }
        ],
        data_quality={"record_count": 1},
    )


def testing_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/testing-spec",
        metadata={
            "contract": "Testing strategy, CI, and coverage contract aligned with the v1.3 specification chapter 9.",
            "test_type_count": len(TESTING_SPEC["strategy"]),
            "coverage_target": "80%",
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **TESTING_SPEC,
            }
        ],
        data_quality={"record_count": 1},
    )


def schedule_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/schedule-spec",
        metadata={
            "contract": "Project phases and milestones aligned with the v1.3 specification chapter 10.",
            "phase_count": len(SCHEDULE_SPEC["phases"]),
            "milestone_count": len(SCHEDULE_SPEC["milestones"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **SCHEDULE_SPEC,
            }
        ],
        data_quality={"record_count": len(SCHEDULE_SPEC["phases"])},
    )


def appendix_spec_response() -> dict[str, Any]:
    return response_envelope(
        endpoint="/api/v1/system/appendix-spec",
        metadata={
            "contract": "Project bootstrap files, templates, and entrypoints aligned with the v1.3 specification chapter 11.",
            "template_count": len(APPENDIX_SPEC["project_templates"]),
        },
        data=[
            {
                "spec_version": SPEC_VERSION,
                **APPENDIX_SPEC,
            }
        ],
        data_quality={"record_count": 1},
    )


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def observation_record(
    observation: TwPortObservation,
    *,
    generated_at: datetime | None = None,
    include_runtime_status: bool = False,
) -> dict[str, Any]:
    generated = generated_at or now_taipei()
    status = observation_status(observation, generated, None) if include_runtime_status else None
    observed_at = observation.obs_time.astimezone(TAIPEI).isoformat()
    fetched_at = observation.fetched_at.astimezone(TAIPEI).isoformat() if observation.fetched_at else None

    return {
        "record_id": stable_record_id(observation),
        "source": observation.source,
        "device_type": observation.device_type,
        "station": {
            "station_id": observation.station_id,
            "station_name": observation.station_name,
            "location": observation.location,
            "port_code": observation.port_code,
            "longitude": observation.longitude,
            "latitude": observation.latitude,
            "elevation": observation.elevation,
        },
        "time": {
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "time_zone": TIME_ZONE,
        },
        "metrics": {
            "wind_speed_mps": observation.wind_speed,
            "wind_gust_mps": observation.wind_gust,
            "wind_direction_deg": observation.wind_direction,
            "wind_gust_direction_deg": observation.wind_gust_direction,
            "precipitation_10min_mm": observation.precipitation_10min,
            "precipitation_1hr_mm": observation.precipitation_1hr,
            "precipitation_24hr_mm": observation.precipitation_24hr,
            "air_temperature_c": observation.air_temperature,
            "relative_humidity_percent": observation.relative_humidity,
            "air_pressure_hpa": observation.air_pressure,
            "visibility_m": observation.visibility,
            "tide_level": observation.tide_level,
            "tide_level_unit": observation.tide_level_unit,
            "wave_height_m": observation.wave_height,
            "wave_period_s": observation.wave_period,
            "wave_max_height_m": observation.wave_max_height,
            "current_speed_mps": observation.current_speed,
            "current_direction_deg": observation.current_direction,
        },
        "quality": {
            "is_forecast": observation.is_forecast,
            "confidence": observation.confidence,
            "stale_at_fetch": observation.stale,
            "status_level": status["status_level"] if status else None,
            "status_label": status["status_label"] if status else None,
            "is_stale_now": status["is_stale_now"] if status else None,
            "obs_age_minutes": status["obs_age_minutes"] if status else None,
            "fetch_age_minutes": status["fetch_age_minutes"] if status else None,
            "threshold_minutes": status["threshold_minutes"] if status else None,
            "expected_update_interval": status["expected_update_interval"] if status else None,
        },
    }


def stable_record_id(observation: TwPortObservation) -> str:
    observed_at = observation.obs_time.astimezone(TAIPEI).isoformat()
    forecast_flag = "forecast" if observation.is_forecast else "observed"
    return ":".join(
        [
            observation.source,
            observation.device_type,
            observation.station_id,
            forecast_flag,
            observed_at,
        ]
    )


def response_envelope(
    *,
    endpoint: str,
    generated_at: datetime | None = None,
    request: dict[str, Any] | None = None,
    data: list[dict[str, Any]] | None = None,
    data_quality: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = generated_at or now_taipei()
    return {
        "schema_version": SCHEMA_VERSION,
        "endpoint": endpoint,
        "generated_at": generated.astimezone(TAIPEI).isoformat(),
        "time_zone": TIME_ZONE,
        "request": request or {},
        "metadata": metadata or {},
        "data_quality": data_quality or {},
        "data": data or [],
    }


def current_response(observations: list[TwPortObservation]) -> dict[str, Any]:
    generated = now_taipei()
    records = [
        observation_record(observation, generated_at=generated, include_runtime_status=True)
        for observation in observations
    ]
    stale_records = [record for record in records if record["quality"]["is_stale_now"]]
    return response_envelope(
        endpoint="/api/v1/microclimate/current",
        generated_at=generated,
        data=records,
        data_quality={
            "record_count": len(records),
            "stale_count": len(stale_records),
            "contains_stale": bool(stale_records),
            "status_method": "Runtime freshness is evaluated by source/device policy at response time.",
        },
        metadata={
            "contract": "Stable flat observation list. New fields may be added only under metadata or a future schema_version.",
        },
    )


def forecast_response(minutes: int, observations: list[TwPortObservation]) -> dict[str, Any]:
    generated = now_taipei()
    return response_envelope(
        endpoint="/api/v1/microclimate/forecast",
        generated_at=generated,
        request={"minutes": minutes},
        data=[
            observation_record(observation, generated_at=generated, include_runtime_status=False)
            for observation in observations
        ],
        data_quality={
            "record_count": len(observations),
            "method": "linear wind_speed projection; persistence when history is insufficient",
            "forecast_horizon_minutes": minutes,
        },
    )


def history_response(
    *,
    source: str,
    hours: int,
    observations: list[TwPortObservation],
    query_start: str | None,
    query_end: str | None,
    note: str,
    source_config: dict[str, Any],
) -> dict[str, Any]:
    generated = now_taipei()
    return response_envelope(
        endpoint="/api/v1/cwa/history",
        generated_at=generated,
        request={"source": source, "hours": hours},
        data=[
            observation_record(observation, generated_at=generated, include_runtime_status=False)
            for observation in observations
        ],
        data_quality={
            "record_count": len(observations),
            "query_start": query_start,
            "query_end": query_end,
            "saved_to_local_db": False,
            "note": note,
        },
        metadata={
            "source_config": source_config,
        },
    )
