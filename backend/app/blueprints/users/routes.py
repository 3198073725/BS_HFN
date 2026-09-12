from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.auth_service import AuthenticationError, get_active_user
from app.utils import error, success
from . import users_bp


@users_bp.get("/me")
@jwt_required()
def current_user():
    try:
        user = get_active_user(get_jwt_identity())
    except AuthenticationError as exc:
        return error(str(exc), 401)
    return success(user.to_dict())
