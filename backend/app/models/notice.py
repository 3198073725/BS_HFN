from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Notice(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "notice"
    __table_args__ = (db.Index("idx_notice_status_time", "status", "publish_time"),)

    created_by = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
    )
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    publish_time = db.Column(db.DateTime)

    creator = db.relationship("User", backref="notices")
