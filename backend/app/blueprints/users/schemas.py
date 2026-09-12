import re


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


class ValidationError(ValueError):
    pass


def validate_profile(payload: dict) -> dict:
    allowed = {"real_name", "email", "phone", "bio"}
    if not any(field in payload for field in allowed):
        raise ValidationError("没有可更新的个人资料")

    result = {}
    if "real_name" in payload:
        real_name = str(payload.get("real_name") or "").strip()
        if not 1 <= len(real_name) <= 50:
            raise ValidationError("姓名不能为空且不能超过50位")
        result["real_name"] = real_name
    if "email" in payload:
        email = _optional_text(payload.get("email"))
        if email and (len(email) > 100 or not EMAIL_PATTERN.fullmatch(email)):
            raise ValidationError("邮箱格式不正确")
        result["email"] = email
    if "phone" in payload:
        phone = _optional_text(payload.get("phone"))
        if phone and not PHONE_PATTERN.fullmatch(phone):
            raise ValidationError("手机号格式不正确")
        result["phone"] = phone
    if "bio" in payload:
        bio = _optional_text(payload.get("bio"))
        if bio and len(bio) > 500:
            raise ValidationError("个人简介不能超过500位")
        result["bio"] = bio
    return result


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
