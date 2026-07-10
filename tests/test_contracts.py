from datetime import datetime

from app.contracts import (
    SCHEMA_VERSION,
    appendix_spec_response,
    api_spec_response,
    current_response,
    data_spec_response,
    deployment_spec_response,
    evaluation_spec_response,
    feature_spec_response,
    model_spec_response,
    observation_record,
    schedule_spec_response,
    schema_response,
    system_info_response,
    system_requirements_response,
    testing_spec_response as build_testing_spec_response,
)
from app.models import TAIPEI, TwPortObservation


def sample_observation() -> TwPortObservation:
    return TwPortObservation(
        source="twport",
        port_code="5",
        station_id="KHWD01M01",
        station_name="高雄港第一港口風力觀測站",
        location="10號碼頭",
        device_type="WIND",
        obs_time=datetime(2026, 7, 2, 18, 40, tzinfo=TAIPEI),
        longitude=120.28,
        latitude=22.61,
        wind_speed=2.5,
        wind_gust=4.1,
        wind_direction=270.0,
        confidence="high",
        stale=False,
        fetched_at=datetime(2026, 7, 2, 18, 43, tzinfo=TAIPEI),
    )


def test_observation_record_has_stable_v1_shape():
    record = observation_record(
        sample_observation(),
        generated_at=datetime(2026, 7, 2, 18, 45, tzinfo=TAIPEI),
        include_runtime_status=True,
    )

    assert set(record) == {"record_id", "source", "device_type", "station", "time", "metrics", "quality"}
    assert record["station"]["station_id"] == "KHWD01M01"
    assert record["time"]["time_zone"] == "Asia/Taipei"
    assert "wind_speed_mps" in record["metrics"]
    assert "precipitation_1hr_mm" in record["metrics"]
    assert "status_level" in record["quality"]
    assert "raw_data" not in record


def test_current_response_uses_schema_version_and_flat_data():
    response = current_response([sample_observation()])

    assert response["schema_version"] == SCHEMA_VERSION
    assert response["endpoint"] == "/api/v1/microclimate/current"
    assert response["data_quality"]["record_count"] == 1
    assert isinstance(response["data"], list)
    assert response["data"][0]["metrics"]["wind_gust_mps"] == 4.1


def test_schema_response_documents_stable_endpoints():
    response = schema_response()

    assert response["schema_version"] == SCHEMA_VERSION
    assert "/api/v1/microclimate/current" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/dispatch/risk" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/info" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/requirements" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/data-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/feature-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/model-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/evaluation-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/api-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/deployment-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/testing-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/schedule-spec" in response["metadata"]["stable_endpoints"]
    assert "/api/v1/system/appendix-spec" in response["metadata"]["stable_endpoints"]
    assert "observation_record" in response["metadata"]


def test_system_info_response_documents_chapter_1_overview():
    response = system_info_response()

    assert response["endpoint"] == "/api/v1/system/info"
    assert response["data_quality"]["record_count"] == 1
    info = response["data"][0]
    assert info["spec_version"] == "v2.0"
    assert info["target_area"]["port_code"] == "KHH"
    assert "data_collection" in info["architecture_layers"]
    assert "wind_speed" in info["prediction_targets"]


def test_system_requirements_response_maps_chapter_2_requirements():
    response = system_requirements_response()

    assert response["endpoint"] == "/api/v1/system/requirements"
    assert response["data_quality"]["record_count"] == 12
    matrix = response["data"][0]
    functional_ids = {item["id"] for item in matrix["functional"]}
    non_functional_ids = {item["id"] for item in matrix["non_functional"]}
    assert functional_ids == {"FR-001", "FR-002", "FR-003", "FR-004", "FR-005", "FR-006", "FR-007"}
    assert non_functional_ids == {"NFR-001", "NFR-002", "NFR-003", "NFR-004", "NFR-005"}
    assert all(item["implementation"] for item in matrix["functional"])


def test_data_spec_response_documents_chapter_3_sources_quality_and_storage():
    response = data_spec_response()

    assert response["endpoint"] == "/api/v1/system/data-spec"
    assert response["metadata"]["source_count"] >= 3
    spec = response["data"][0]
    source_ids = {source["id"] for source in spec["sources"]}
    assert {"cwa", "codis", "twport"}.issubset(source_ids)
    assert spec["variables"]["wind_speed"]["valid_range"] == [0, 60]
    assert spec["quality_standards"]["station_missing_ratio_max"] == 0.10
    assert "microclimate_observations" == spec["storage"]["sqlite_table"]
    assert "summary" in spec["quality_report_schema"]


def test_feature_spec_response_documents_chapter_4_feature_taxonomy():
    response = feature_spec_response()

    assert response["endpoint"] == "/api/v1/system/feature-spec"
    assert response["metadata"]["category_count"] >= 7
    spec = response["data"][0]
    category_ids = {category["id"] for category in spec["categories"]}
    assert {"historical_lag", "rolling_statistics", "meteorological_physics", "interaction"}.issubset(category_ids)
    assert spec["generation"]["lag_hours"] == [0.5, 1, 2, 3, 6]
    assert "pressure_change_3h" in spec["key_features_by_target"]["precipitation_1hr"]
    assert spec["selection"]["correlation_threshold_default"] == 0.95


def test_model_spec_response_documents_chapter_5_model_strategy():
    response = model_spec_response()

    assert response["endpoint"] == "/api/v1/system/model-spec"
    assert response["metadata"]["target_model_count"] == 5
    spec = response["data"][0]
    assert spec["strategy"]["modeling_unit"] == "per_target_variable"
    assert "precipitation_1hr" in spec["target_models"]
    assert "RainfallCascadeModel" in spec["target_models"]["precipitation_1hr"]["implemented_models"]
    assert "BaseWeatherModel" in spec["model_classes"]
    assert "train_model" in spec["training_pipeline"]


def test_evaluation_spec_response_documents_chapter_6_strategy():
    response = evaluation_spec_response()

    assert response["endpoint"] == "/api/v1/system/evaluation-spec"
    assert response["metadata"]["basic_metric_count"] >= 8
    spec = response["data"][0]
    assert "skill_score" in spec["basic_metrics"]
    assert "hss" in spec["rainfall_metrics"]["classification_metrics"]
    assert "ets" in spec["rainfall_metrics"]["classification_metrics"]
    assert spec["validation"]["time_series_split"]["test_size"] == 0.2
    assert spec["reporting"]["format"] == "Markdown"


def test_api_spec_response_documents_chapter_7_internal_api_and_cli():
    response = api_spec_response()

    assert response["endpoint"] == "/api/v1/system/api-spec"
    spec = response["data"][0]
    assert {"DataAPI", "FeatureAPI", "ModelAPI"} == set(spec["internal_python_api"])
    assert "download" in spec["cli"]["commands"]
    assert "run-all" in spec["cli"]["commands"]
    assert "/api/v1/dispatch/risk" in spec["http_api"]["stable_endpoints"]
    assert "/api/v1/system/deployment-spec" in spec["http_api"]["stable_endpoints"]
    assert "/api/v1/system/testing-spec" in spec["http_api"]["stable_endpoints"]


def test_deployment_spec_response_documents_chapter_8_deployment_contract():
    response = deployment_spec_response()

    assert response["endpoint"] == "/api/v1/system/deployment-spec"
    assert response["metadata"]["minimum_cpu_cores"] == 4
    spec = response["data"][0]
    assert spec["hardware"]["recommended"]["memory_gb"] == 16
    assert spec["software"]["python"] == "3.9+"
    assert "DATA_DIR" in spec["environment_variables"]["required_for_runtime"]
    assert spec["logging"]["config_path"] == "config/logging_config.yaml"
    assert spec["monitoring"]["health_endpoint"] == "/health"


def test_testing_spec_response_documents_chapter_9_testing_contract():
    response = build_testing_spec_response()

    assert response["endpoint"] == "/api/v1/system/testing-spec"
    assert response["metadata"]["test_type_count"] == 4
    spec = response["data"][0]
    assert spec["strategy"][0]["type"] == "unit"
    assert spec["strategy"][0]["target"] == "coverage > 80%"
    assert spec["ci"]["workflow"] == ".github/workflows/ci.yml"
    assert "3.9" in spec["ci"]["python_versions"]


def test_schedule_spec_response_documents_chapter_10_timeline():
    response = schedule_spec_response()

    assert response["endpoint"] == "/api/v1/system/schedule-spec"
    assert response["metadata"]["phase_count"] == 5
    assert response["metadata"]["milestone_count"] == 5
    spec = response["data"][0]
    assert spec["phases"][0]["id"] == "phase_1"
    assert spec["milestones"][-1]["id"] == "M5"
    assert spec["timeline_format"] == "mermaid_gantt"


def test_appendix_spec_response_documents_chapter_11_templates():
    response = appendix_spec_response()

    assert response["endpoint"] == "/api/v1/system/appendix-spec"
    spec = response["data"][0]
    assert spec["project_templates"]["setup_project_structure"]["linux"] == "scripts/setup_project_structure.sh"
    assert spec["project_templates"]["package_setup"] == "setup.py"
    assert "tests" in spec["documented_tree"]
    assert spec["entrypoints"]["cli"] == "python -m kaohsiung_microclimate_lstm.src.cli"
