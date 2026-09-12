from sqlalchemy import func

from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin


class Notification(IdMixin, db.Model):
    __tablename__ = "notification"
    __table_args__ = (
        db.Index("idx_notification_recipient_time", "recipient_id", "created_at"),
        db.Index("idx_notification_recipient_read", "recipient_id", "read_at"),
    )

    recipient_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    sender_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
    )
    category = db.Column(db.String(50), nullable=False, default="SYSTEM", server_default="SYSTEM")
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255))
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    recipient = db.relationship("User", foreign_keys=[recipient_id], backref="notifications")
    sender = db.relationship("User", foreign_keys=[sender_id])
