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


def validate_update(payload) -> dict:
    result = {}
    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not 1 <= len(title) <= 150:
            raise ValidationError("视频标题不能为空且不能超过150位")
        result["title"] = title
    if "description" in payload:
        description = str(payload.get("description") or "").strip() or None
        if description and len(description) > 500:
            raise ValidationError("视频描述不能超过500位")
        result["description"] = description
    if "sort_order" in payload:
        try:
            sort_order = int(payload.get("sort_order"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("视频排序参数不正确") from exc
        if sort_order < 0 or sort_order > 100000:
            raise ValidationError("视频排序必须在0到100000之间")
        result["sort_order"] = sort_order
    if not result:
        raise ValidationError("没有可更新的视频内容")
    return result


def validate_replacement(form) -> dict:
    result = validate_update(form)
    if "title" not in result:
        raise ValidationError("请输入视频标题")
    result.setdefault("description", None)
    result.setdefault("sort_order", 0)
    return result
