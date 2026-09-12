class ValidationError(ValueError):
    pass


def validate_category(payload: dict, *, partial: bool = False) -> dict:
    data = {}
    if not partial or "name" in payload:
        name = str(payload.get("name", "")).strip()
        if not 1 <= len(name) <= 50:
            raise ValidationError("分类名称不能为空且不能超过50位")
        data["name"] = name
    if not partial or "description" in payload:
        description = str(payload.get("description") or "").strip() or None
        if description and len(description) > 255:
            raise ValidationError("分类说明不能超过255位")
        data["description"] = description
    if not partial or "sort_order" in payload:
        try:
            sort_order = int(payload.get("sort_order", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationError("分类排序必须是整数") from exc
        if not 0 <= sort_order <= 100000:
            raise ValidationError("分类排序必须在0到100000之间")
        data["sort_order"] = sort_order
    if partial and not data:
        raise ValidationError("没有可更新的分类字段")
    return data
