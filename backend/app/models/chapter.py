from app.extensions import db
from .base import BIGINT_UNSIGNED, IdMixin, TimestampMixin


class Chapter(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "chapter"
    __table_args__ = (db.Index("idx_chapter_course_sort", "course_id", "sort_order"),)

    course_id = db.Column(
        BIGINT_UNSIGNED,
        db.ForeignKey("course.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(500))
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    course = db.relationship("Course", backref=db.backref("chapters", cascade="all, delete-orphan"))
