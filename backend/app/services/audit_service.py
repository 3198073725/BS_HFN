from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.datetime_utils import iso_utc
from app.extensions import db
from app.models import AdminAuditLog, User


def record_admin_action(
    admin_id: int,
    action: str,
    resource_type: str,
    resource_id: int | None,
    summary: str,
    *,
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    log = AdminAuditLog(
        admin_id=admin_id,
        action=action[:50],
        resource_type=resource_type[:50],
        resource_id=resource_id,
        summary=summary[:500],
        details=details or None,
        ip_address=(ip_address or "")[:45] or None,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.session.add(log)
    db.session.commit()


def list_admin_audit_logs(
    page: int,
    page_size: int,
    *,
    action: str | None = None,
    resource_type: str | None = None,
    keyword: str | None = None,
) -> dict:
    statement = db.select(AdminAuditLog).options(joinedload(AdminAuditLog.admin))
    if action:
        statement = statement.where(AdminAuditLog.action == action)
    if resource_type:
        statement = statement.where(AdminAuditLog.resource_type == resource_type)
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.join(User, AdminAuditLog.admin_id == User.id).where(
            or_(
                AdminAuditLog.summary.ilike(pattern),
                User.username.ilike(pattern),
                User.real_name.ilike(pattern),
            )
        )
    pagination = db.paginate(
        statement.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()),
        page=page,
        per_page=page_size,
        error_out=False,
    )
    return {
        "items": [serialize_admin_audit_log(item) for item in pagination.items],
        "pagination": _pagination_payload(pagination),
    }


def serialize_admin_audit_log(log: AdminAuditLog) -> dict:
    return {
        "id": log.id,
        "admin_id": log.admin_id,
        "admin_username": log.admin.username,
        "admin_name": log.admin.real_name,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "summary": log.summary,
        "details": log.details,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "created_at": iso_utc(log.created_at),
    }


def _pagination_payload(pagination) -> dict:
    return {
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    }
