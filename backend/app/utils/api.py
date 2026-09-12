from flask import jsonify, request
from werkzeug.exceptions import BadRequest


class JsonBodyError(ValueError):
    pass


def json_body() -> dict:
    if not request.is_json:
        return {}
    try:
        payload = request.get_json(silent=False)
    except BadRequest as exc:
        raise JsonBodyError("请求体不是有效的 JSON") from exc
    if not isinstance(payload, dict):
        raise JsonBodyError("请求体必须是 JSON 对象")
    return payload


def success(data=None, message="success", status=200):
    return jsonify(code=status, message=message, data=data), status


def error(message, status=400, data=None):
    return jsonify(code=status, message=message, data=data), status
