from datetime import datetime, timezone
import hashlib
import hmac

from flask import current_app
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt import PyJWTError
from redis import RedisError


class TokenStoreUnavailable(RuntimeError):
    pass


class InvalidCompanionToken(ValueError):
    pass


def credential_signature(password_hash: str) -> str:
    """Bind every session to current credentials without exposing the hash."""
    secret = str(current_app.config["JWT_SECRET_KEY"]).encode()
    return hmac.new(secret, password_hash.encode(), hashlib.sha256).hexdigest()


def decode_owned_token(encoded_token: str, expected_subject: str | int) -> dict:
    try:
        payload = decode_token(encoded_token)
    except (JWTExtendedException, PyJWTError, TypeError, ValueError) as exc:
        raise InvalidCompanionToken("附加 Token 无效或已过期") from exc
    if payload.get("sub") != str(expected_subject):
        raise InvalidCompanionToken("附加 Token 不属于当前用户")
    if payload.get("type") not in {"access", "refresh"}:
        raise InvalidCompanionToken("附加 Token 类型不正确")
    return payload


def revoke_token(payload: dict) -> None:
    jti = payload["jti"]
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    ttl = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 1)
    if current_app.config["TESTING"]:
        current_app.extensions["testing_jwt_blocklist"].add(jti)
        return
    try:
        current_app.extensions["redis"].setex(f"jwt:blocklist:{jti}", ttl, "1")
    except RedisError as exc:
        raise TokenStoreUnavailable("Redis 不可用，暂时无法安全退出") from exc
