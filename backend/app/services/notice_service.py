from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.constants import NoticeStatus
from app.extensions import db
from app.models import Notice


class NoticeNotFound(ValueError):
    pass


class NoticeConflict(ValueError):
    pass


def list_published_notices() -> list[dict]:
    notices = db.session.scalars(
        _notice_query()
        .where(Notice.status == NoticeStatus.PUBLISHED.value)
        .order_by(Notice.publish_time.desc(), Notice.id.desc())
    ).all()
    return [serialize_notice(item) for item in notices]


def list_all_notices() -> list[dict]:
    notices = db.session.scalars(
        _notice_query().order_by(Notice.created_at.desc(), Notice.id.desc())
    ).all()
    return [serialize_notice(item) for item in notices]


def create_notice(admin_id: int, data: dict) -> dict:
    notice = Notice(created_by=admin_id, status=NoticeStatus.DRAFT.value, **data)
    db.session.add(notice)
    db.session.commit()
    return serialize_notice(_get_notice(notice.id))


def update_notice(notice_id: int, data: dict) -> dict:
    notice = _get_notice(notice_id)
    if notice.status == NoticeStatus.PUBLISHED.value:
        raise NoticeConflict("已发布公告需先下线后再编辑")
    for field, value in data.items():
        setattr(notice, field, value)
    db.session.commit()
    return serialize_notice(notice)


def change_notice_status(notice_id: int, status: NoticeStatus) -> dict:
    notice = _get_notice(notice_id)
    if status is NoticeStatus.PUBLISHED:
        if notice.status not in {NoticeStatus.DRAFT.value, NoticeStatus.OFFLINE.value}:
            raise NoticeConflict("当前公告不能发布")
        notice.publish_time = _now()
    elif status is NoticeStatus.OFFLINE:
        if notice.status != NoticeStatus.PUBLISHED.value:
            raise NoticeConflict("只有已发布公告可以下线")
    notice.status = status.value
    db.session.commit()
    return serialize_notice(notice)


def delete_notice(notice_id: int) -> None:
    notice = _get_notice(notice_id)
    if notice.status == NoticeStatus.PUBLISHED.value:
        raise NoticeConflict("已发布公告不能直接删除")
    db.session.delete(notice)
    db.session.commit()


def serialize_notice(notice: Notice) -> dict:
    return {
        "id": notice.id,
        "created_by": notice.created_by,
        "creator_name": notice.creator.real_name if notice.creator else None,
        "title": notice.title,
        "content": notice.content,
        "status": notice.status,
        "publish_time": _iso(notice.publish_time),
        "created_at": _iso(notice.created_at),
        "updated_at": _iso(notice.updated_at),
    }


def _notice_query():
    return db.select(Notice).options(joinedload(Notice.creator))


def _get_notice(notice_id: int) -> Notice:
    notice = db.session.scalar(_notice_query().where(Notice.id == notice_id))
    if notice is None:
        raise NoticeNotFound("公告不存在")
    return notice


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
