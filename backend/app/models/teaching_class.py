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
