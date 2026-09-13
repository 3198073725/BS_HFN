from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math


class ValidationError(ValueError):
    pass


def validate_exam(payload: dict, partial: bool = False) -> dict:
    data = {}
    if not partial or "exam_type" in payload:
        exam_type = str(payload.get("exam_type", "ONLINE")).upper()
        if exam_type not in {"ONLINE", "ATTACHMENT"}:
            raise ValidationError("测验方式必须为在线答题或附件试卷")
        data["exam_type"] = exam_type
    if not partial or "course_id" in payload:
        data["course_id"] = _positive_int(payload.get("course_id"), "课程")
    if not partial or "title" in payload:
        data["title"] = _text(payload.get("title"), "测验名称", 200)
    if "description" in payload:
        description = str(payload.get("description") or "").strip()
        if len(description) > 10000:
            raise ValidationError("测验说明不能超过10000位")
        data["description"] = description or None
    if not partial or "total_score" in payload:
        data["total_score"] = _score(payload.get("total_score", 100), "测验总分", Decimal("9999.99"))
    if "start_time" in payload:
        data["start_time"] = _datetime(payload.get("start_time"), "开始时间")
    if "end_time" in payload:
        data["end_time"] = _datetime(payload.get("end_time"), "结束时间")
    if "time_limit_minutes" in payload:
        raw_limit = payload.get("time_limit_minutes")
        if raw_limit in (None, ""):
            data["time_limit_minutes"] = None
        else:
            limit = _positive_int(raw_limit, "限时")
            if limit > 1440:
                raise ValidationError("测验限时不能超过1440分钟")
            data["time_limit_minutes"] = limit
    if partial and not data:
        raise ValidationError("没有可更新的测验内容")
    start = data.get("start_time")
    end = data.get("end_time")
    if start and end and start >= end:
        raise ValidationError("测验结束时间必须晚于开始时间")
    return data


def validate_question(payload: dict) -> dict:
    question_type = str(payload.get("question_type") or "").strip().upper()
    if question_type not in {"SINGLE", "JUDGE"}:
        raise ValidationError("试题类型仅支持单选题和判断题")
    data = {
        "question_type": question_type,
        "content": _text(payload.get("content"), "题目内容", 10000),
        "score": _score(payload.get("score"), "题目分值", Decimal("999.99")),
        "sort_order": _non_negative_int(payload.get("sort_order", 0), "题目排序"),
    }
    if question_type == "SINGLE":
        options = payload.get("options") if isinstance(payload.get("options"), dict) else payload
        for key in ("A", "B", "C", "D"):
            value = options.get(key) if options is not payload else options.get(f"option_{key.lower()}")
            text = str(value or "").strip()
            if key in {"A", "B"} and not text:
                raise ValidationError("单选题至少需要A、B两个选项")
            if len(text) > 500:
                raise ValidationError(f"选项{key}不能超过500位")
            data[f"option_{key.lower()}"] = text or None
        answer = str(payload.get("correct_answer") or "").strip().upper()
        if answer not in {"A", "B", "C", "D"} or not data[f"option_{answer.lower()}"]:
            raise ValidationError("单选题正确答案必须对应一个有效选项")
    else:
        data.update(option_a=None, option_b=None, option_c=None, option_d=None)
        answer = str(payload.get("correct_answer") or "").strip().upper()
        aliases = {"TRUE": "TRUE", "FALSE": "FALSE", "正确": "TRUE", "错误": "FALSE"}
        answer = aliases.get(answer, "")
        if not answer:
            raise ValidationError("判断题正确答案必须是TRUE或FALSE")
    data["correct_answer"] = answer
    return data


def validate_answers(payload: dict) -> dict[int, str]:
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        raise ValidationError("答案必须使用列表格式")
    answers = {}
    for item in raw_answers:
        if not isinstance(item, dict):
            raise ValidationError("答案项目格式不正确")
        question_id = _positive_int(item.get("question_id"), "试题")
        if question_id in answers:
            raise ValidationError("同一道试题不能重复提交答案")
        answer = str(item.get("answer") or "").strip().upper()
        if len(answer) > 500:
            raise ValidationError("单个答案不能超过500位")
        answers[question_id] = answer
    return answers


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


def _non_negative_int(value, label: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{label}参数不正确")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label}参数不正确") from exc
    if parsed < 0 or parsed > 100000:
        raise ValidationError(f"{label}参数不正确")
    return parsed


def _text(value, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not 1 <= len(text) <= maximum:
        raise ValidationError(f"{label}不能为空且不能超过{maximum}位")
    return text


def _datetime(value, label: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{label}格式不正确") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _score(value, label: str, maximum: Decimal) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError(f"{label}必须是数字")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{label}必须是数字") from exc
    if not math.isfinite(float(number)) or number <= 0 or number > maximum:
        raise ValidationError(f"{label}必须大于0且不能超过{maximum}")
    return number.quantize(Decimal("0.01"))
