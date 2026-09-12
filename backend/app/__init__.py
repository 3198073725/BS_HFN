import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from .config import CONFIG_MAP
from .extensions import cors, db, init_celery, init_jwt_callbacks, jwt, migrate


def create_app(config_name: str | None = None) -> Flask:
    selected = config_name or os.getenv("FLASK_ENV", "development")
    config = CONFIG_MAP.get(selected)
    if config is None:
        raise ValueError(f"Unknown FLASK_ENV: {selected}")

    app = Flask(__name__)
    app.config.from_object(config)
    app.json.ensure_ascii = False
    validate_runtime_configuration(app, selected)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    init_jwt_callbacks(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})
    if app.config["CELERY_ENABLED"]:
        init_celery(app)

    from . import models  # noqa: F401
    from .blueprints import register_blueprints

    register_blueprints(app)
    register_error_handlers(app)
    register_request_guards(app)
    register_development_media(app)
    create_runtime_directories(app)
    return app


def create_runtime_directories(app: Flask) -> None:
    media_root = Path(app.config["MEDIA_ROOT"])
    for relative in (
        "avatars",
        "course_covers",
        "videos/original",
        "videos/processed",
        "videos/hls",
        "videos/covers",
        "homework",
    ):
        (media_root / relative).mkdir(parents=True, exist_ok=True)


def register_error_handlers(app: Flask) -> None:
    from .utils import JsonBodyError

    @app.errorhandler(JsonBodyError)
    def invalid_json_body(error):
        return jsonify(code=400, message=str(error), data=None), 400

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(code=404, message="资源不存在", data=None), 404

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify(code=413, message="请求内容超过大小限制", data=None), 413

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify(code=405, message="请求方法不允许", data=None), 405

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("未处理的服务器异常：%s", error)
        db.session.rollback()
        return jsonify(code=500, message="服务器内部错误", data=None), 500


def register_request_guards(app: Flask) -> None:
    @app.before_request
    def reject_oversized_json():
        limit = int(app.config["MAX_JSON_CONTENT_LENGTH"])
        if request.is_json and request.content_length and request.content_length > limit:
            abort(413)


def register_development_media(app: Flask) -> None:
    if app.config["DEBUG"]:
        @app.get("/media/<path:filename>")
        def media_file(filename: str):
            return send_from_directory(app.config["MEDIA_ROOT"], filename)


def validate_runtime_configuration(app: Flask, selected: str) -> None:
    if selected != "production":
        return
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = str(app.config.get(key, ""))
        if len(value) < 32 or value.startswith(("development-only", "replace-with")):
            raise RuntimeError(f"生产环境必须配置至少32位的 {key}")
