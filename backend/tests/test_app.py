def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "ok"


def test_expected_blueprints_are_registered(app):
    expected = {
        "admin",
        "auth",
        "courses",
        "exams",
        "homework",
        "learning",
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
