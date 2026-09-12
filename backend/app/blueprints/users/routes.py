from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.auth_service import AuthenticationError, get_active_user
from app.services.user_profile_service import (
    ProfileConflict,
    ProfileNotFound,
    delete_avatar,
    get_public_profile,
    update_avatar,
    update_profile,
)
from app.utils import error, json_body, success
from . import users_bp
from .schemas import ValidationError, validate_profile


@users_bp.get("/me")
@jwt_required()
def current_user():
    try:
        user = get_active_user(get_jwt_identity())
    except AuthenticationError as exc:
        return error(str(exc), 401)
    return success(user.to_dict())


@users_bp.put("/me")
@jwt_required()
def edit_current_user():
    try:
        user = update_profile(int(get_jwt_identity()), validate_profile(json_body()))
    except ValidationError as exc:
        return error(str(exc), 400)
    except ProfileNotFound as exc:
        return error(str(exc), 404)
    except ProfileConflict as exc:
        return error(str(exc), 409)
    return success(user, "个人资料已更新")


@users_bp.post("/me/avatar")
@jwt_required()
def upload_current_user_avatar():
    avatar = request.files.get("avatar")
    if avatar is None:
        return error("请选择头像图片", 400)
    try:
        user = update_avatar(int(get_jwt_identity()), avatar)
    except ProfileNotFound as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 400)
    return success(user, "头像已更新")


@users_bp.delete("/me/avatar")
@jwt_required()
def remove_current_user_avatar():
    try:
        user = delete_avatar(int(get_jwt_identity()))
    except ProfileNotFound as exc:
        return error(str(exc), 404)
    return success(user, "头像已移除")


@users_bp.get("/<int:user_id>")
def public_user_profile(user_id: int):
    try:
        profile = get_public_profile(user_id)
    except ProfileNotFound as exc:
        return error(str(exc), 404)
    return success(profile)
