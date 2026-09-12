from sqlalchemy import func

from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin


class AdminAuditLog(IdMixin, db.Model):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        db.Index("idx_admin_audit_admin_time", "admin_id", "created_at"),
        db.Index("idx_admin_audit_resource", "resource_type", "resource_id"),
        db.Index("idx_admin_audit_action_time", "action", "created_at"),
    )

    admin_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    action = db.Column(db.String(50), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(BIGINT_UNSIGNED)
    summary = db.Column(db.String(500), nullable=False)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    admin = db.relationship("User", backref="admin_audit_logs")
