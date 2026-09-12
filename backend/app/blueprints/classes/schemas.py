class ValidationError(ValueError):
    pass


def validate_classroom(payload: dict, partial: bool = False) -> dict:
    result = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not 1 <= len(name) <= 100:
            raise ValidationError("班级名称不能为空且不能超过100位")
        result["name"] = name
    if "description" in payload:
        description = str(payload.get("description") or "").strip() or None
        if description and len(description) > 500:
            raise ValidationError("班级说明不能超过500位")
        result["description"] = description
    if partial and not result:
        raise ValidationError("没有可更新的班级内容")
    return result


def validate_student_account(payload: dict) -> str:
    account = str(payload.get("account") or "").strip()
    if not 1 <= len(account) <= 100:
        raise ValidationError("请输入不超过100位的学生账号、学号或邮箱")
    return account


def validate_course_id(payload: dict) -> int:
    try:
        course_id = int(payload.get("course_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("请选择要关联的课程") from exc
    if course_id <= 0:
        raise ValidationError("请选择要关联的课程")
    return course_id
