from flask import Blueprint


notices_bp = Blueprint("notices", __name__)


from . import routes  # noqa: E402, F401
