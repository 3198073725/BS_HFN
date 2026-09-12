class ValidationError(ValueError):
    pass


def validate_upload(form) -> dict:
    title = str(form.get("title", "")).strip()
    description = str(form.get("description", "")).strip() or None
    try:
        chapter_id = int(form.get("chapter_id", 0))
        sort_order = int(form.get("sort_order", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("章节或排序参数不正确") from exc
    if chapter_id <= 0:
        raise ValidationError("必须选择课程章节")
    if sort_order < 0 or sort_order > 100000:
        raise ValidationError("视频排序必须在0到100000之间")
    if not 1 <= len(title) <= 150:
        raise ValidationError("视频标题不能为空且不能超过150位")
    if description and len(description) > 500:
        raise ValidationError("视频描述不能超过500位")
    return {
        "chapter_id": chapter_id,
        "title": title,
        "description": description,
        "sort_order": sort_order,
    }
