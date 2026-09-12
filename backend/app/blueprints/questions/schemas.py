import math

from app.constants import QuestionStatus


class ValidationError(ValueError):
    pass


def validate_question(payload: dict) -> dict:
    if isinstance(payload.get("video_id"), bool):
        raise ValidationError("视频参数不正确")
    try:
        video_id = int(payload.get("video_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("视频参数不正确") from exc
    if video_id <= 0:
        raise ValidationError("视频参数不正确")

    video_time = _number(payload.get("video_time", 0), "提问时间点")
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    if not 1 <= len(title) <= 200:
        raise ValidationError("问题标题不能为空且不能超过200位")
    if not 1 <= len(content) <= 5000:
        raise ValidationError("问题内容不能为空且不能超过5000位")
    return {"video_id": video_id, "video_time": video_time, "title": title, "content": content}


def validate_answer(payload: dict) -> str:
    content = str(payload.get("content", "")).strip()
    if not 1 <= len(content) <= 5000:
        raise ValidationError("回答内容不能为空且不能超过5000位")
    return content


def validate_filters(args) -> tuple[str | None, int | None]:
    status = str(args.get("status", "")).strip().upper() or None
    if status is not None and status not in {item.value for item in QuestionStatus}:
        raise ValidationError("问题状态参数不正确")
    raw_video_id = args.get("video_id")
    if raw_video_id in (None, ""):
        return status, None
    try:
        video_id = int(raw_video_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("视频参数不正确") from exc
    if video_id <= 0:
        raise ValidationError("视频参数不正确")
    return status, video_id


def _number(value, label: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{label}必须是数字")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label}必须是数字") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValidationError(f"{label}不能小于0")
    return round(parsed, 3)
