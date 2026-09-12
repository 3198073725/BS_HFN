"""Celery worker 入口。

Windows 开发环境请使用 solo 进程池：
celery -A celery_worker.celery_app worker --pool=solo --loglevel=info
"""

from app import create_app


flask_app = create_app()
celery_app = flask_app.extensions["celery"]
