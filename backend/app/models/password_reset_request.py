from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class PasswordResetRequest(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "password_reset_request"
    __table_args__ = (
        db.Index("idx_password_reset_student_status", "student_id", "status"),
        db.Index("idx_password_reset_status_expiry", "status", "expires_at"),
    )

    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    requested_password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PENDING", server_default="PENDING")
    reviewer_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
    )
    reviewed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, nullable=False)

    student = db.relationship("User", foreign_keys=[student_id], backref="password_reset_requests")
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
