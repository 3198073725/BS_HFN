from flask import request

from app.constants import UserRole
from app.services.auth_service import ConflictError, create_user
from app.utils import error, roles_required, success
from app.blueprints.auth.schemas import ValidationError, validate_managed_user
from . import admin_bp


@admin_bp.post("/users")
@roles_required(UserRole.ADMIN)
def create_managed_user():
    try:
        data = validate_managed_user(request.get_json(silent=True) or {})
        user = create_user(data, data["role"])
    except ValidationError as exc:
        return error(str(exc), 400)
    except ConflictError as exc:
        return error(str(exc), 409)
    return success(user.to_dict(), "用户创建成功", 201)
