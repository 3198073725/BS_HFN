from app.extensions import db
from sqlalchemy.dialects.mysql import VARCHAR
from .base import BIGINT_UNSIGNED, IdMixin


class LearningProgressReceipt(IdMixin, db.Model):
    """Durable acknowledgements committed atomically with progress increments."""

    __tablename__ = "learning_progress_receipt"
    __table_args__ = (
        db.UniqueConstraint("student_id", "request_id", name="uk_progress_receipt_request"),
    )
    student_id = db.Column(BIGINT_UNSIGNED, db.ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    video_id = db.Column(BIGINT_UNSIGNED, db.ForeignKey("video.id", ondelete="CASCADE"), nullable=False)
    request_id = db.Column(db.String(100).with_variant(VARCHAR(100, charset="ascii", collation="ascii_bin"), "mysql"), nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    response = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    video = db.relationship("Video", backref=db.backref("progress_receipts", cascade="all, delete-orphan"))
