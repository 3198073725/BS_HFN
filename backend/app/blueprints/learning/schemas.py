import math
import re


class ValidationError(ValueError):
    pass


def validate_progress(payload: dict) -> dict:
    current_time = _number(payload.get("current_time"), "当前播放位置")
    raw_delta = payload.get("watch_duration_delta", 0)
    if isinstance(raw_delta, bool):
        raise ValidationError("本次观看时长必须是整数")
    try:
        watch_delta = int(raw_delta)
    except (TypeError, ValueError) as exc:
        raise ValidationError("本次观看时长必须是整数") from exc
    if watch_delta < 0 or watch_delta > 60:
        raise ValidationError("本次观看时长必须在0到60秒之间")
    request_id = payload.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", request_id)):
        raise ValidationError("进度请求编号须为1到100位字母、数字或安全分隔符")
    return {"current_time": current_time, "watch_delta": watch_delta, "request_id": request_id}


def validate_note(payload: dict, partial: bool = False) -> dict:
    result = {}
    if not partial or "video_time" in payload:
        result["video_time"] = _number(payload.get("video_time"), "笔记时间点")
    if not partial or "content" in payload:
        content = str(payload.get("content", "")).strip()
        if not 1 <= len(content) <= 2000:
            raise ValidationError("笔记内容不能为空且不能超过2000位")
        result["content"] = content
    if partial and not result:
        raise ValidationError("没有可更新的笔记内容")
    return result


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
