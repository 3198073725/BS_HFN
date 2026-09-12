from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class LearningRecord(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "learning_record"
    __table_args__ = (
        db.UniqueConstraint("student_id", "video_id", name="uk_learning_student_video"),
        db.Index("idx_learning_student_time", "student_id", "last_watch_time"),
        db.Index("idx_learning_video", "video_id"),
        db.Index("idx_learning_status", "student_id", "status"),
    )

    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    video_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("video.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    current_time = db.Column(db.Numeric(10, 3), nullable=False, default=0, server_default="0")
    watch_duration = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    progress = db.Column(db.Numeric(5, 2), nullable=False, default=0, server_default="0")
    status = db.Column(db.String(20), nullable=False, default="LEARNING", server_default="LEARNING")
    last_watch_time = db.Column(db.DateTime)

    student = db.relationship("User", backref="learning_records")
    video = db.relationship("Video", backref="learning_records")


class VideoNote(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "video_note"
    __table_args__ = (
        db.Index("idx_note_student", "student_id", "created_at"),
        db.Index("idx_note_video", "video_id", "video_time"),
    )

    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    video_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("video.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    video_time = db.Column(db.Numeric(10, 3), nullable=False, default=0, server_default="0")
    content = db.Column(db.Text, nullable=False)

    student = db.relationship("User", backref="video_notes")
    video = db.relationship("Video", backref="notes")
