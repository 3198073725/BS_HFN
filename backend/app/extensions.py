from celery import Celery, Task
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()


def init_celery(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery = Celery(app.import_name, task_cls=FlaskTask)
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        imports=("app.tasks.video_tasks",),
        task_ignore_result=True,
        task_track_started=True,
        timezone="Asia/Shanghai",
    )
    celery.set_default()
    app.extensions["celery"] = celery
    return celery


def init_jwt_callbacks(app: Flask) -> None:
    from redis import Redis, RedisError
    import hmac
    from app.models import User
    from app.services.token_service import credential_signature

    redis_client = Redis.from_url(app.config["REDIS_URL"], decode_responses=True)
    app.extensions["redis"] = redis_client
    app.extensions["testing_jwt_blocklist"] = set()

    @jwt.token_in_blocklist_loader
    def is_token_revoked(_header, payload):
        try:
            user = db.session.get(User, int(payload["sub"]))
        except (KeyError, TypeError, ValueError):
            return True
        signature = payload.get("credentials")
        if (user is None or not user.status or not isinstance(signature, str)
                or not hmac.compare_digest(signature, credential_signature(user.password_hash))):
            return True
        jti = payload["jti"]
        if app.config["TESTING"]:
            return jti in app.extensions["testing_jwt_blocklist"]
        try:
            return bool(redis_client.exists(f"jwt:blocklist:{jti}"))
        except RedisError:
            app.logger.exception("Redis 不可用，JWT 校验按安全策略拒绝请求")
            return True

    @jwt.unauthorized_loader
    def missing_token(message):
        return {"code": 401, "message": message, "data": None}, 401

    @jwt.invalid_token_loader
    def invalid_token(message):
        return {"code": 401, "message": message, "data": None}, 401

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return {"code": 401, "message": "Token 已过期", "data": None}, 401

    @jwt.revoked_token_loader
    def revoked_token(_header, _payload):
        return {"code": 401, "message": "Token 已失效", "data": None}, 401
