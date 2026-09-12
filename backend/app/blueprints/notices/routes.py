from flask import request
from flask_jwt_extended import get_jwt_identity

from app.constants import UserRole
from app.services.notice_service import (
    NoticeConflict,
    NoticeNotFound,
    change_notice_status,
    create_notice,
    delete_notice,
    list_all_notices,
    list_published_notices,
    update_notice,
)
from app.utils import error, roles_required, success
from . import notices_bp
from .schemas import ValidationError, validate_notice, validate_status


@notices_bp.get("")
def public_notices():
    return success(list_published_notices())


@notices_bp.get("/manage")
@roles_required(UserRole.ADMIN)
def managed_notices():
    return success(list_all_notices())


@notices_bp.post("")
@roles_required(UserRole.ADMIN)
def add_notice():
    try:
        data = validate_notice(request.get_json(silent=True) or {})
        notice = create_notice(int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    return success(notice, "公告创建成功", 201)


@notices_bp.put("/<int:notice_id>")
@roles_required(UserRole.ADMIN)
def edit_notice(notice_id: int):
    try:
        data = validate_notice(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(update_notice(notice_id, data), "公告更新成功"))


@notices_bp.put("/<int:notice_id>/status")
@roles_required(UserRole.ADMIN)
def set_notice_status(notice_id: int):
    try:
        status = validate_status(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return error(str(exc), 400)
    return _handle(lambda: success(change_notice_status(notice_id, status), "公告状态更新成功"))


@notices_bp.delete("/<int:notice_id>")
@roles_required(UserRole.ADMIN)
def remove_notice(notice_id: int):
    return _handle(lambda: _delete_response(notice_id))


def _delete_response(notice_id: int):
    delete_notice(notice_id)
    return success(message="公告删除成功")


def _handle(action):
    try:
        return action()
    except NoticeNotFound as exc:
        return error(str(exc), 404)
    except NoticeConflict as exc:
        return error(str(exc), 409)
