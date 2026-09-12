from flask import Blueprint

from app.utils import success


system_bp = Blueprint("system", __name__)


@system_bp.get("/health")
def health():
    return success({"service": "student-tutoring-api", "status": "ok"})
