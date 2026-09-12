from sqlalchemy import func

from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class TeachingClass(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "teaching_class"
    __table_args__ = (
        db.UniqueConstraint("teacher_id", "name", name="uk_teaching_class_teacher_name"),
        db.Index("idx_teaching_class_teacher", "teacher_id"),
    )

    teacher_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))

    teacher = db.relationship("User", foreign_keys=[teacher_id], backref="managed_classes")


class TeachingClassStudent(IdMixin, db.Model):
    __tablename__ = "teaching_class_student"
    __table_args__ = (
        db.UniqueConstraint("class_id", "student_id", name="uk_teaching_class_student"),
        db.Index("idx_teaching_class_student_student", "student_id"),
    )

    class_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("teaching_class.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    joined_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    classroom = db.relationship(
        "TeachingClass",
        backref=db.backref("student_links", cascade="all, delete-orphan"),
    )
    student = db.relationship("User", backref="teaching_class_links")


class TeachingClassCourse(IdMixin, db.Model):
    __tablename__ = "teaching_class_course"
    __table_args__ = (
        db.UniqueConstraint("class_id", "course_id", name="uk_teaching_class_course"),
        db.Index("idx_teaching_class_course_course", "course_id"),
    )

    class_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("teaching_class.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    assigned_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    classroom = db.relationship(
        "TeachingClass",
        backref=db.backref("course_links", cascade="all, delete-orphan"),
    )
    course = db.relationship("Course", backref="teaching_class_links")


class TeachingClassJoinRequest(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "teaching_class_join_request"
    __table_args__ = (
        db.UniqueConstraint("class_id", "student_id", name="uk_class_join_request_student"),
        db.Index("idx_class_join_request_class_status", "class_id", "status"),
        db.Index("idx_class_join_request_student_status", "student_id", "status"),
    )

    class_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("teaching_class.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    source_course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="SET NULL", onupdate="CASCADE"),
    )
    status = db.Column(db.String(20), nullable=False, default="PENDING", server_default="PENDING")
    reviewer_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
    )
    reviewed_at = db.Column(db.DateTime)

    classroom = db.relationship(
        "TeachingClass",
        backref=db.backref("join_requests", cascade="all, delete-orphan"),
    )
    student = db.relationship("User", foreign_keys=[student_id], backref="class_join_requests")
    source_course = db.relationship("Course", foreign_keys=[source_course_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
