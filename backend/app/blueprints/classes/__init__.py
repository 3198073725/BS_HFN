from flask import Blueprint


classes_bp = Blueprint("classes", __name__)


from . import routes  # noqa: E402, F401
