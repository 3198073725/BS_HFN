import re


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]{3,50}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


class ValidationError(ValueError):
    pass


def validate_registration(payload: dict) -> dict:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    real_name = str(payload.get("real_name", "")).strip()
    email = _optional_text(payload, "email")
    phone = _optional_text(payload, "phone")
    student_no = _optional_text(payload, "student_no")

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError("用户名需为3到50位中文、字母、数字或下划线")
    if not 8 <= len(password) <= 72:
        raise ValidationError("密码长度需为8到72位")
    if not 1 <= len(real_name) <= 50:
        raise ValidationError("真实姓名不能为空且不能超过50位")
    if email and not EMAIL_PATTERN.fullmatch(email):
        raise ValidationError("邮箱格式不正确")
    if email and len(email) > 100:
        raise ValidationError("邮箱不能超过100位")
    if phone and not PHONE_PATTERN.fullmatch(phone):
        raise ValidationError("手机号格式不正确")
    if student_no and len(student_no) > 50:
        raise ValidationError("学号不能超过50位")

    return {
        "username": username,
        "password": password,
        "real_name": real_name,
        "email": email,
        "phone": phone,
        "student_no": student_no,
    }


def validate_login(payload: dict) -> tuple[str, str]:
    account = str(payload.get("account", payload.get("username", ""))).strip()
    password = str(payload.get("password", ""))
    if not account or not password:
        raise ValidationError("账号和密码不能为空")
    if len(account) > 100:
        raise ValidationError("账号不能超过100位")
    if len(password) > 72:
        raise ValidationError("密码不能超过72位")
    return account, password


def validate_password_reset(payload: dict) -> tuple[str, str, str]:
    username = str(payload.get("username") or "").strip()
    verification = str(payload.get("verification") or "").strip()
    password = validate_new_password(payload)
    if not username or len(username) > 50:
        raise ValidationError("请输入正确的用户名")
    if not verification or len(verification) > 100:
        raise ValidationError("请输入注册邮箱、学号、工号或手机号进行身份核验")
    return username, verification, password


def validate_new_password(payload: dict) -> str:
    password = str(payload.get("new_password", payload.get("password", "")))
    if not 8 <= len(password) <= 72:
        raise ValidationError("新密码长度需为8到72位")
    return password


def validate_managed_user(payload: dict) -> dict:
    data = validate_registration(payload)
    role = str(payload.get("role", "")).upper()
    if role not in {"TEACHER", "STUDENT"}:
        raise ValidationError("管理员只能创建教师或学生账号")
    teacher_no = _optional_text(payload, "teacher_no")
    if teacher_no and len(teacher_no) > 50:
        raise ValidationError("工号不能超过50位")
    if role == "TEACHER" and not teacher_no:
        raise ValidationError("教师账号必须提供 teacher_no")
    if role == "STUDENT" and not data["student_no"]:
        raise ValidationError("学生账号必须提供 student_no")
    if role == "TEACHER" and data["student_no"]:
        raise ValidationError("教师账号不能提供 student_no")
    if role == "STUDENT" and teacher_no:
        raise ValidationError("学生账号不能提供 teacher_no")
    data.update(role=role, teacher_no=teacher_no)
    return data


def _optional_text(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None
