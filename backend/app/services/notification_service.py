from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import CourseStudent, Notification
from app.services.course_task_access_service import class_task_access_condition


class NotificationNotFound(ValueError):
    pass


def queue_notification(
    recipient_id: int,
    title: str,
    content: str,
    *,
    category: str = "SYSTEM",
    sender_id: int | None = None,
    link: str | None = None,
) -> Notification:
    notification = Notification(
        recipient_id=recipient_id,
        sender_id=sender_id,
        category=category[:50],
        title=title[:200],
        content=content,
        link=link[:255] if link else None,
    )
    db.session.add(notification)
    return notification


def queue_course_notifications(
    course_id: int,
    title: str,
    content: str,
    *,
    category: str,
    sender_id: int,
    link: str,
) -> None:
    student_ids = db.session.scalars(
        db.select(CourseStudent.student_id).where(
            CourseStudent.course_id == course_id,
            CourseStudent.status.is_(True),
            class_task_access_condition(course_id, CourseStudent.student_id),
        )
    ).all()
    for student_id in set(student_ids):
        queue_notification(
            student_id,
            title,
            content,
            category=category,
            sender_id=sender_id,
            link=link,
        )


def list_notifications(user_id: int, page: int, page_size: int, unread_only: bool = False) -> dict:
    statement = (
        db.select(Notification)
        .options(joinedload(Notification.sender))
        .where(Notification.recipient_id == user_id)
    )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    pagination = db.paginate(
        statement.order_by(Notification.created_at.desc(), Notification.id.desc()),
        page=page,
        per_page=page_size,
        error_out=False,
    )
    unread_count = db.session.scalar(
        db.select(func.count(Notification.id)).where(
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
        )
    ) or 0
    return {
        "items": [serialize_notification(item) for item in pagination.items],
        "unread_count": int(unread_count),
        "pagination": {
            "page": pagination.page,
            "page_size": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }


def mark_notification_read(notification_id: int, user_id: int) -> dict:
    notification = db.session.scalar(
        db.select(Notification)
        .options(joinedload(Notification.sender))
        .where(Notification.id == notification_id, Notification.recipient_id == user_id)
    )
    if notification is None:
        raise NotificationNotFound("通知不存在")
    if notification.read_at is None:
        notification.read_at = utc_now()
        db.session.commit()
    return serialize_notification(notification)


def mark_all_notifications_read(user_id: int) -> int:
    unread = db.session.scalars(
        db.select(Notification).where(
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
        )
    ).all()
    now = utc_now()
    for item in unread:
        item.read_at = now
    db.session.commit()
    return len(unread)


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "category": notification.category,
        "title": notification.title,
        "content": notification.content,
        "link": notification.link,
        "sender_name": notification.sender.real_name if notification.sender else "系统",
        "read": notification.read_at is not None,
        "read_at": iso_utc(notification.read_at),
        "created_at": iso_utc(notification.created_at),
    }
