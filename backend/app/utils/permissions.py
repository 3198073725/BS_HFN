from functools import wraps

from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models import User
from .api import error


def roles_required(*roles):
    allowed = {str(role) for role in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            verify_jwt_in_request()
            user = db.session.get(User, int(get_jwt_identity()))
            if user is None or not user.status:
                return error("用户不存在或已禁用", 401)
            if user.role not in allowed:
                return error("无权执行此操作", 403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
