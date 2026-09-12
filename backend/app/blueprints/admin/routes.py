from flask import request

from app.constants import UserRole
from app.services.auth_service import ConflictError, create_user
from app.services.admin_service import AdminConflict, AdminNotFound, change_user_status, list_users
from app.utils import error, json_body, roles_required, success
from app.blueprints.auth.schemas import ValidationError, validate_managed_user
from . import admin_bp


@admin_bp.get("/users")
@roles_required(UserRole.ADMIN)
def users():
    role = str(request.args.get("role") or "").strip().upper() or None
    if role and role not in {item.value for item in UserRole}:
        return error("用户角色参数不正确", 400)
    raw_status = str(request.args.get("status") or "").strip().lower()
    if raw_status and raw_status not in {"true", "false", "1", "0"}:
        return error("用户状态参数不正确", 400)
    status = raw_status in {"true", "1"} if raw_status else None
    keyword = str(request.args.get("keyword") or "").strip() or None
    if keyword and len(keyword) > 100:
        return error("搜索关键词不能超过100位", 400)
    return success(list_users(role, status, keyword))


@admin_bp.post("/users")
@roles_required(UserRole.ADMIN)
def create_managed_user():
    try:
        data = validate_managed_user(json_body())
        user = create_user(data, data["role"])
    except ValidationError as exc:
        return error(str(exc), 400)
    except ConflictError as exc:
        return error(str(exc), 409)
    return success(user.to_dict(), "用户创建成功", 201)


@admin_bp.put("/users/<int:user_id>/status")
@roles_required(UserRole.ADMIN)
def set_user_status(user_id: int):
    raw_status = json_body().get("status")
    if not isinstance(raw_status, bool):
        return error("用户状态必须是布尔值", 400)
    try:
        user = change_user_status(user_id, raw_status)
    except AdminNotFound as exc:
        return error(str(exc), 404)
    except AdminConflict as exc:
        return error(str(exc), 409)
    return success(user, "用户状态更新成功")
