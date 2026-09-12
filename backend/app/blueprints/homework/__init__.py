from flask import Blueprint


homework_bp = Blueprint("homework", __name__)


from . import routes  # noqa: E402, F401
