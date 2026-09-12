def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "ok"


def test_api_method_not_allowed_uses_json_response(client):
    response = client.post("/api/health")

    assert response.status_code == 405
    assert response.is_json
    assert response.get_json()["message"] == "请求方法不允许"


def test_json_requests_have_a_separate_size_limit(app, client):
    app.config["MAX_JSON_CONTENT_LENGTH"] = 32
    response = client.post(
        "/api/auth/login",
        json={"account": "a" * 64, "password": "password"},
    )

    assert response.status_code == 413


def test_expected_blueprints_are_registered(app):
    expected = {
        "admin",
        "auth",
        "courses",
        "exams",
        "homework",
        "learning",
        "notices",
        "questions",
        "statistics",
        "system",
        "users",
        "videos",
    }

    assert expected.issubset(app.blueprints)


def test_testing_config_isolated_from_local_async_setting(app):
    assert app.config["CELERY_ENABLED"] is False
    assert app.config["VIDEO_PROCESSING_ASYNC"] is False
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {}
