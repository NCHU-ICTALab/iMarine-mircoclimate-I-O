from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app


def test_system_info_endpoint_returns_v13_overview():
    client = TestClient(app)

    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "microclimate.v1"
    assert body["endpoint"] == "/api/v1/system/info"
    assert body["data"][0]["spec_version"] == "v1.3"
    assert body["data"][0]["runtime_model_version"] == "kaohsiung_port_dispatch_risk_v1.3"
    assert body["data"][0]["target_area"]["port_code"] == "KHH"


def test_system_requirements_endpoint_returns_chapter_2_matrix():
    client = TestClient(app)

    response = client.get("/api/v1/system/requirements")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/requirements"
    assert body["metadata"]["functional_count"] == 7
    assert body["metadata"]["non_functional_count"] == 5
    assert body["data"][0]["functional"][0]["id"] == "FR-001"


def test_system_data_spec_endpoint_returns_chapter_3_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/data-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/data-spec"
    assert body["metadata"]["variable_count"] >= 10
    assert body["data"][0]["storage"]["sqlite_table"] == "microclimate_observations"
    assert "precipitation_1hr" in body["data"][0]["variables"]


def test_system_feature_spec_endpoint_returns_chapter_4_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/feature-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/feature-spec"
    assert body["metadata"]["category_count"] >= 7
    assert "wind_speed_gust" in body["data"][0]["key_features_by_target"]


def test_system_model_spec_endpoint_returns_chapter_5_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/model-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/model-spec"
    assert body["metadata"]["target_model_count"] == 5
    assert "wind_gust" in body["data"][0]["target_models"]


def test_system_evaluation_spec_endpoint_returns_chapter_6_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/evaluation-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/evaluation-spec"
    assert body["metadata"]["rainfall_metric_count"] >= 9
    assert "extreme_capture_rate" in body["data"][0]["extreme_value_assessment"]["metrics"]


def test_system_api_spec_endpoint_returns_chapter_7_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/api-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/api-spec"
    assert body["metadata"]["internal_api_count"] == 3
    assert "features" in body["data"][0]["cli"]["commands"]


def test_system_deployment_spec_endpoint_returns_chapter_8_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/deployment-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/deployment-spec"
    assert body["metadata"]["minimum_memory_gb"] == 8
    assert body["data"][0]["installation"]["linux_script"] == "install.sh"


def test_system_testing_spec_endpoint_returns_chapter_9_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/testing-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/testing-spec"
    assert body["metadata"]["coverage_target"] == "80%"
    assert body["data"][0]["ci"]["provider"] == "GitHub Actions"


def test_system_schedule_spec_endpoint_returns_chapter_10_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/schedule-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/schedule-spec"
    assert body["metadata"]["phase_count"] == 5
    assert body["data"][0]["milestones"][0]["id"] == "M1"


def test_system_appendix_spec_endpoint_returns_chapter_11_contract():
    client = TestClient(app)

    response = client.get("/api/v1/system/appendix-spec")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/v1/system/appendix-spec"
    assert body["data"][0]["project_templates"]["makefile"] == "Makefile"
