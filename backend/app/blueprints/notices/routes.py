from flask import current_app, request
from flask_jwt_extended import get_jwt_identity

from app.constants import UserRole
from app.extensions import db
from app.services.audit_service import record_admin_action
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
from app.utils import error, json_body, roles_required, success
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
        data = validate_notice(json_body())
        notice = create_notice(int(get_jwt_identity()), data)
    except ValidationError as exc:
        return error(str(exc), 400)
    _record_audit("NOTICE_CREATE", notice["id"], f"创建公告草稿：{notice['title']}")
    return success(notice, "公告创建成功", 201)


@notices_bp.put("/<int:notice_id>")
@roles_required(UserRole.ADMIN)
def edit_notice(notice_id: int):
    try:
        data = validate_notice(json_body(), partial=True)
    except ValidationError as exc:
        return error(str(exc), 400)
    def action():
        notice = update_notice(notice_id, data)
        _record_audit("NOTICE_UPDATE", notice_id, f"更新公告：{notice['title']}")
        return success(notice, "公告更新成功")

    return _handle(action)


@notices_bp.put("/<int:notice_id>/status")
@roles_required(UserRole.ADMIN)
def set_notice_status(notice_id: int):
    try:
        status = validate_status(json_body())
    except ValidationError as exc:
        return error(str(exc), 400)
    def action():
        notice = change_notice_status(notice_id, status)
        _record_audit(
            "NOTICE_STATUS_CHANGE",
            notice_id,
            f"将公告 {notice['title']} 设为{status.value}",
            {"status": status.value},
        )
        return success(notice, "公告状态更新成功")

    return _handle(action)


@notices_bp.delete("/<int:notice_id>")
@roles_required(UserRole.ADMIN)
def remove_notice(notice_id: int):
    return _handle(lambda: _delete_response(notice_id))


def _delete_response(notice_id: int):
    delete_notice(notice_id)
    _record_audit("NOTICE_DELETE", notice_id, f"删除公告：#{notice_id}")
    return success(message="公告删除成功")


def _handle(action):
    try:
        return action()
    except NoticeNotFound as exc:
        return error(str(exc), 404)
    except NoticeConflict as exc:
        return error(str(exc), 409)


def _record_audit(
    action: str,
    notice_id: int,
    summary: str,
    details: dict | None = None,
) -> None:
    try:
        record_admin_action(
            int(get_jwt_identity()),
            action,
            "NOTICE",
            notice_id,
            summary,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("公告操作审计写入失败：%s", action)
