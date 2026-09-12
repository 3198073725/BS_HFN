from flask import jsonify


def success(data=None, message="success", status=200):
    return jsonify(code=status, message=message, data=data), status


def error(message, status=400, data=None):
    return jsonify(code=status, message=message, data=data), status
