from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math


class ValidationError(ValueError):
    pass


def validate_homework(payload: dict, partial: bool = False) -> dict:
    data = {}
    if not partial or "course_id" in payload:
        data["course_id"] = _positive_int(payload.get("course_id"), "课程")
    if not partial or "title" in payload:
        data["title"] = _text(payload.get("title"), "作业标题", 200)
    if not partial or "description" in payload:
        data["description"] = _text(payload.get("description"), "作业说明", 10000)
    if "deadline" in payload:
        data["deadline"] = _datetime(payload.get("deadline"))
    if not partial or "total_score" in payload:
        data["total_score"] = _score(payload.get("total_score", 100), "作业满分", allow_zero=False)
    if partial and not data:
        raise ValidationError("没有可更新的作业内容")
    return data


def validate_submission(payload: dict) -> str:
    return _text(payload.get("content"), "作业内容", 20000)


def validate_grade(payload: dict) -> tuple[Decimal, str | None]:
    score = _score(payload.get("score"), "作业得分", allow_zero=True)
    comment = str(payload.get("teacher_comment") or "").strip()
    if len(comment) > 10000:
        raise ValidationError("教师评语不能超过10000位")
    return score, comment or None


def _positive_int(value, label: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{label}参数不正确")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label}参数不正确") from exc
    if parsed <= 0:
        raise ValidationError(f"{label}参数不正确")
    return parsed


def _text(value, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not 1 <= len(text) <= maximum:
        raise ValidationError(f"{label}不能为空且不能超过{maximum}位")
    return text


def _datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("截止时间格式不正确") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _score(value, label: str, allow_zero: bool) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError(f"{label}必须是数字")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{label}必须是数字") from exc
    if not math.isfinite(float(number)):
        raise ValidationError(f"{label}必须是有限数字")
    minimum = Decimal("0") if allow_zero else Decimal("0.01")
    if number < minimum or number > Decimal("999.99"):
        comparator = "大于等于0" if allow_zero else "大于0"
        raise ValidationError(f"{label}必须{comparator}且不能超过999.99")
    return number.quantize(Decimal("0.01"))
