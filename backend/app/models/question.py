from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Question(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "question"
    __table_args__ = (
        db.Index("idx_question_student", "student_id", "created_at"),
        db.Index("idx_question_video", "video_id", "video_time"),
        db.Index("idx_question_status", "status", "created_at"),
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
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="WAITING", server_default="WAITING")

    student = db.relationship("User", backref="questions")
    video = db.relationship(
        "Video",
        backref=db.backref("questions", cascade="all, delete-orphan"),
    )


class Answer(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "answer"
    __table_args__ = (
        db.UniqueConstraint("question_id", name="uk_answer_question"),
        db.Index("idx_answer_teacher", "teacher_id", "created_at"),
    )

    question_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("question.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    teacher_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    content = db.Column(db.Text, nullable=False)

    question = db.relationship(
        "Question",
        backref=db.backref("answer", uselist=False, cascade="all, delete-orphan"),
    )
    teacher = db.relationship("User", backref="answers")
