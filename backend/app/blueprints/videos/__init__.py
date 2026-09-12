from flask import Blueprint


videos_bp = Blueprint("videos", __name__)


from . import routes  # noqa: E402, F401
