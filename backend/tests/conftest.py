import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app(tmp_path):
    application = create_app("testing")
    application.config["MEDIA_ROOT"] = tmp_path / "media"
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()
