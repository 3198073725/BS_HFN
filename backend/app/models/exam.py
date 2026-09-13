from sqlalchemy import func

from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Exam(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "exam"
    __table_args__ = (
        db.Index("idx_exam_course", "course_id", "status"),
        db.Index("idx_exam_teacher", "teacher_id"),
        db.Index("idx_exam_time", "start_time", "end_time"),
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
    description = db.Column(db.Text)
    attachment = db.Column(db.String(500))
    attachment_name = db.Column(db.String(255))
    total_score = db.Column(db.Numeric(6, 2), nullable=False, default=100, server_default="100")
    status = db.Column(db.String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    time_limit_minutes = db.Column(db.Integer)
    published_at = db.Column(db.DateTime)

    course = db.relationship(
        "Course",
        backref=db.backref("exams", cascade="all, delete-orphan"),
    )
    teacher = db.relationship("User", backref="created_exams")


class ExamQuestion(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "exam_question"
    __table_args__ = (
        db.Index("idx_exam_question_sort", "exam_id", "sort_order"),
        db.Index("idx_exam_question_type", "exam_id", "question_type"),
    )

    exam_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("exam.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    question_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500))
    option_b = db.Column(db.String(500))
    option_c = db.Column(db.String(500))
    option_d = db.Column(db.String(500))
    correct_answer = db.Column(db.String(20), nullable=False)
    score = db.Column(db.Numeric(5, 2), nullable=False, default=0, server_default="0")
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    exam = db.relationship("Exam", backref=db.backref("questions", cascade="all, delete-orphan"))


class ExamRecord(IdMixin, db.Model):
    __tablename__ = "exam_record"
    __table_args__ = (
        db.UniqueConstraint("exam_id", "student_id", name="uk_exam_record"),
        db.Index("idx_exam_record_student", "student_id", "submit_time"),
        db.Index("idx_exam_record_exam_score", "exam_id", "score"),
    )

    exam_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("exam.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    score = db.Column(db.Numeric(6, 2), nullable=False, default=0, server_default="0")
    correct_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    wrong_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    status = db.Column(db.String(20), nullable=False, default="DOING", server_default="DOING")
    started_at = db.Column(db.DateTime)
    submit_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    exam = db.relationship(
        "Exam",
        backref=db.backref("records", cascade="all, delete-orphan"),
    )
    student = db.relationship("User", backref="exam_records")


class ExamAnswer(IdMixin, db.Model):
    __tablename__ = "exam_answer"
    __table_args__ = (
        db.UniqueConstraint("exam_record_id", "question_id", name="uk_exam_answer"),
        db.Index("idx_exam_answer_question", "question_id"),
    )

    exam_record_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("exam_record.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    question_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("exam_question.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_answer = db.Column(db.String(500))
    is_correct = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    score = db.Column(db.Numeric(5, 2), nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    record = db.relationship(
        "ExamRecord",
        backref=db.backref("answers", cascade="all, delete-orphan"),
    )
    question = db.relationship(
        "ExamQuestion",
        backref=db.backref("student_answers", cascade="all, delete-orphan"),
    )
