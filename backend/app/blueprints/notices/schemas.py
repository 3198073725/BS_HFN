from app.constants import NoticeStatus


class ValidationError(ValueError):
    pass


def validate_notice(payload: dict, partial: bool = False) -> dict:
    data = {}
    if not partial or "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not 1 <= len(title) <= 200:
            raise ValidationError("公告标题不能为空且不能超过200位")
        data["title"] = title
    if not partial or "content" in payload:
        content = str(payload.get("content") or "").strip()
        if not 1 <= len(content) <= 50000:
            raise ValidationError("公告内容不能为空且不能超过50000位")
        data["content"] = content
    if partial and not data:
        raise ValidationError("没有可更新的公告内容")
    return data


def validate_status(payload: dict) -> NoticeStatus:
    raw = str(payload.get("status") or "").strip().upper()
    if raw not in {NoticeStatus.PUBLISHED.value, NoticeStatus.OFFLINE.value}:
        raise ValidationError("公告状态只能设置为PUBLISHED或OFFLINE")
    return NoticeStatus(raw)
