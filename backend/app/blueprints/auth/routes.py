from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.services.auth_service import (
    AuthenticationError,
    ConflictError,
    authenticate,
    create_student,
    get_active_user,
    issue_token_pair,
)
from app.services.token_service import (
    InvalidCompanionToken,
    TokenStoreUnavailable,
    decode_owned_token,
    revoke_token,
)
from app.utils import error, json_body, success
from . import auth_bp
from .schemas import ValidationError, validate_login, validate_registration


@auth_bp.post("/register")
def register():
    try:
        data = validate_registration(json_body())
        user = create_student(data)
    except ValidationError as exc:
        return error(str(exc), 400)
    except ConflictError as exc:
        return error(str(exc), 409)
    return success(issue_token_pair(user), "注册成功", 201)


@auth_bp.post("/login")
def login():
    try:
        account, password = validate_login(json_body())
        user = authenticate(account, password)
    except ValidationError as exc:
        return error(str(exc), 400)
    except AuthenticationError as exc:
        return error(str(exc), 401)
    return success(issue_token_pair(user), "登录成功")


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    try:
        user = get_active_user(get_jwt_identity())
        revoke_token(get_jwt())
    except AuthenticationError as exc:
        return error(str(exc), 401)
    except TokenStoreUnavailable as exc:
        return error(str(exc), 503)
    return success(issue_token_pair(user), "Token 刷新成功")


@auth_bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    current_payload = get_jwt()
    subject = get_jwt_identity()
    try:
        payloads = [current_payload]
        body = json_body()
        for field in ("access_token", "refresh_token"):
            encoded = body.get(field)
            if encoded:
                payloads.append(decode_owned_token(str(encoded), subject))
        seen = set()
        for payload in payloads:
            if payload["jti"] not in seen:
                revoke_token(payload)
                seen.add(payload["jti"])
    except InvalidCompanionToken as exc:
        return error(str(exc), 400)
    except TokenStoreUnavailable as exc:
        return error(str(exc), 503)
    return success(message="退出成功")
