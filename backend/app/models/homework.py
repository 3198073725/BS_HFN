from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Homework(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "homework"
    __table_args__ = (
        db.Index("idx_homework_course", "course_id", "status"),
        db.Index("idx_homework_teacher", "teacher_id"),
        db.Index("idx_homework_deadline", "status", "deadline"),
    )

    course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    teacher_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    attachment = db.Column(db.String(500))
    deadline = db.Column(db.DateTime)
    total_score = db.Column(db.Numeric(5, 2), nullable=False, default=100, server_default="100")
    status = db.Column(db.String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    published_at = db.Column(db.DateTime)

    course = db.relationship(
        "Course",
        backref=db.backref("homeworks", cascade="all, delete-orphan"),
    )
    teacher = db.relationship("User", backref="created_homeworks")


class HomeworkSubmission(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "homework_submission"
    __table_args__ = (
        db.UniqueConstraint("homework_id", "student_id", name="uk_submission_homework_student"),
        db.Index("idx_submission_student", "student_id", "submit_time"),
        db.Index("idx_submission_homework_status", "homework_id", "status"),
    )

    homework_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("homework.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    content = db.Column(db.Text)
    attachment = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default="SUBMITTED", server_default="SUBMITTED")
    score = db.Column(db.Numeric(5, 2))
    teacher_comment = db.Column(db.Text)
    submit_time = db.Column(db.DateTime)
    graded_time = db.Column(db.DateTime)

    homework = db.relationship(
        "Homework",
        backref=db.backref("submissions", cascade="all, delete-orphan"),
    )
    student = db.relationship("User", backref="homework_submissions")
