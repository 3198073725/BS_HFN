from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.notification_service import (
    NotificationNotFound,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.utils import error, success
from . import notifications_bp


@notifications_bp.get("")
@jwt_required()
def notifications():
    paging = _pagination()
    if not isinstance(paging, dict):
        return paging
    unread_only = str(request.args.get("unread_only", "false")).lower() == "true"
    return success(list_notifications(_user_id(), **paging, unread_only=unread_only))


@notifications_bp.put("/<int:notification_id>/read")
@jwt_required()
def read_notification(notification_id: int):
    try:
        return success(mark_notification_read(notification_id, _user_id()), "通知已读")
    except NotificationNotFound as exc:
        return error(str(exc), 404)


@notifications_bp.put("/read-all")
@jwt_required()
def read_all_notifications():
    count = mark_all_notifications_read(_user_id())
    return success({"updated": count}, "全部通知已读")


def _pagination():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        return error("分页参数必须是整数", 400)
    if page < 1 or page_size < 1 or page_size > 100:
        return error("分页参数超出允许范围", 400)
    return {"page": page, "page_size": page_size}


def _user_id() -> int:
    return int(get_jwt_identity())
