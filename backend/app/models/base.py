from sqlalchemy import func
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT

from app.extensions import db


BIGINT_UNSIGNED = (
    db.BigInteger()
    .with_variant(db.Integer(), "sqlite")
    .with_variant(MYSQL_BIGINT(unsigned=True), "mysql")
)


class IdMixin:
    id = db.Column(BIGINT_UNSIGNED, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
