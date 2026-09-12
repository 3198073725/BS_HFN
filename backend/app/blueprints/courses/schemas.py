class ValidationError(ValueError):
    pass


def validate_course(payload: dict, partial: bool = False) -> dict:
    result = {}
    if not partial or "name" in payload:
        name = str(payload.get("name", "")).strip()
        if not 1 <= len(name) <= 100:
            raise ValidationError("课程名称不能为空且不能超过100位")
        result["name"] = name

    if not partial or "category_id" in payload:
        result["category_id"] = _positive_int(payload.get("category_id"), "课程分类")

    for field, limit in (("description", 500), ("detail", 10000)):
        if field in payload:
            value = str(payload.get(field) or "").strip() or None
            if value and len(value) > limit:
                raise ValidationError(f"{field} 不能超过{limit}位")
            result[field] = value
    return result


def validate_chapter(payload: dict, partial: bool = False) -> dict:
    result = {}
    if not partial or "title" in payload:
        title = str(payload.get("title", "")).strip()
        if not 1 <= len(title) <= 150:
            raise ValidationError("章节标题不能为空且不能超过150位")
        result["title"] = title
    if "description" in payload:
        description = str(payload.get("description") or "").strip() or None
        if description and len(description) > 500:
            raise ValidationError("章节描述不能超过500位")
        result["description"] = description
    if "sort_order" in payload:
        try:
            result["sort_order"] = int(payload["sort_order"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("章节排序必须是整数") from exc
    return result


def _positive_int(value, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label}参数不正确") from exc
    if parsed <= 0:
        raise ValidationError(f"{label}参数不正确")
    return parsed
