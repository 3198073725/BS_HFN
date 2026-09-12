from sqlalchemy import func

from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Course(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "course"
    __table_args__ = (
        db.Index("idx_course_teacher", "teacher_id"),
        db.Index("idx_course_category", "category_id"),
        db.Index("idx_course_status", "status"),
        db.Index("idx_course_category_status", "category_id", "status"),
    )

    teacher_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    category_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course_category.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    cover = db.Column(db.String(255))
    description = db.Column(db.String(500))
    detail = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    published_at = db.Column(db.DateTime)

    teacher = db.relationship("User", foreign_keys=[teacher_id], backref="teaching_courses")
    category = db.relationship("CourseCategory", backref="courses")


class CourseStudent(IdMixin, db.Model):
    __tablename__ = "course_student"
    __table_args__ = (
        db.UniqueConstraint("course_id", "student_id", name="uk_course_student"),
        db.Index("idx_course_student_student", "student_id"),
        db.Index("idx_course_student_status", "course_id", "status"),
    )

    course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    join_time = db.Column(db.DateTime, nullable=False, server_default=func.now())
    status = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    course = db.relationship("Course", backref="student_links")
    student = db.relationship("User", backref="joined_course_links")


class Favorite(IdMixin, db.Model):
    __tablename__ = "favorite"
    __table_args__ = (
        db.UniqueConstraint("student_id", "course_id", name="uk_favorite_student_course"),
        db.Index("idx_favorite_course", "course_id"),
    )

    student_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("sys_user.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    student = db.relationship("User", backref="favorites")
    course = db.relationship("Course", backref="favorite_links")
